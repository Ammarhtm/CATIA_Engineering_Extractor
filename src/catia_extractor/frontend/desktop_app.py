"""CATIA Engineering Extractor | desktop control center (Windows).

Place this file at src/catia_extractor/pipeline_unified/desktop_app.py
Run from project root: python -m catia_extractor.pipeline_unified.desktop_app

Uses existing COM, Vision, OCR, Validation, Final Report and Export modules.
No automatic human approval: the reviewer explicitly chooses each decision.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    # Pillow provides high-quality, aspect-ratio-safe image previews.
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

from catia_extractor.pipeline_unified.human_review import (
    _fingerprint,
    _hash_file,
    _save,
    _summary,
)

ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = ROOT / "output" / "pipeline_unified"
VALIDATION = REPORT_DIR / "validation_report.json"
UNIFIED = REPORT_DIR / "engineering_report.json"
HUMAN = REPORT_DIR / "human_review_report.json"

BG = "#0B1220"
SIDE = "#0E1728"
CARD = "#152238"
CARD2 = "#192943"
FIELD = "#101B2D"
LINE = "#273A54"
TEXT = "#F1F5FB"
MUTED = "#9BAFC7"
ACCENT = "#22C8B0"
BLUE = "#5A9CF8"
AMBER = "#F4BE66"
RED = "#F37F88"

FIELDS = (
    ("geometric_symbol", "Geometric symbol"),
    ("tolerance", "Tolerance"),
    ("diameter_modifier", "Diameter modifier"),
    ("material_condition_modifier", "Material condition"),
    ("datum_references", "Datums (A,B,C)"),
)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Not a JSON object: {path}")
    return data


class ReviewStore:
    """Prepare/sign the same report schema as the original CLI human_review.py."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        base = root / "output" / "pipeline_unified"
        self.path = base / "human_review_report.json"
        self.validation_path = base / "validation_report.json"
        self.unified_path = base / "engineering_report.json"
        self.report = None

    def prepare(self) -> dict:
        validation = read_json(self.validation_path)
        unified = read_json(self.unified_path)
        if not _valid_evidence_for_paths(validation, unified, self.unified_path):
            raise ValueError("Validation report is stale or refers to another CATIA run")
        previous = read_json(self.path) if self.path.is_file() else {}
        old_rows = {r["annotation_id"]: r for r in previous.get("results", [])}
        run_utc = unified["run_utc"]
        rows, seen = [], set()
        for record in validation.get("results", []):
            key = record.get("annotation_id")
            if not key or key in seen:
                raise ValueError(f"Missing or duplicated annotation_id: {key!r}")
            seen.add(key)
            path_text = record.get("review_image")
            image_path = Path(path_text) if path_text else None
            digest = _hash_file(image_path) if image_path else None
            fingerprint = _fingerprint(record, run_utc, digest)
            old = old_rows.get(key, {})
            valid_previous = old.get("evidence_fingerprint") == fingerprint
            saved = old if valid_previous else {}
            rows.append({
                "annotation_id": key,
                "annotation_name": record.get("annotation_name"),
                "validation_status": record.get("status"),
                "issues": record.get("issues", []),
                "review_image": str(image_path) if image_path else "",
                "image_sha256": digest,
                "evidence_fingerprint": fingerprint,
                "original_values": record.get("extracted_values", {}),
                "reviewed_values": saved.get("reviewed_values"),
                "decision": saved.get("decision", "pending"),
                "engineering_approval": saved.get("engineering_approval", False),
                "reviewer": saved.get("reviewer"),
                "reviewed_at_utc": saved.get("reviewed_at_utc"),
                "notes": saved.get("notes", ""),
                "previous_evidence_changed": bool(old) and not valid_previous,
            })
        self.report = {
            "review_version": "human-review-v1",
            "document": validation.get("document"),
            "source_run_utc": run_utc,
            "source_validation_report": str(self.validation_path),
            "engineering_approval": False,
            "results": rows,
        }
        self.persist()
        return self.report

    def persist(self) -> None:
        if self.report is None:
            raise RuntimeError("Review has not been prepared")
        _summary(self.report)
        _save(self.path, self.report)

    def decide(self, index: int, decision: str, reviewer: str = "", notes: str = "", values=None):
        if self.report is None:
            raise RuntimeError("No review report")
        row = self.report["results"][index]
        reviewer, notes = reviewer.strip(), notes.strip()
        if decision not in {"approved", "corrected_and_approved", "rejected", "pending"}:
            raise ValueError("Unsupported review decision")
        if decision in {"approved", "corrected_and_approved", "rejected"} and not reviewer:
            raise ValueError("Reviewer name / ID is required")
        if decision in {"approved", "corrected_and_approved"}:
            if row["validation_status"] == "blocked" or not row["image_sha256"]:
                raise ValueError("Approval blocked: review image or evidence is missing")
            if (row["issues"] or decision == "corrected_and_approved") and not notes:
                raise ValueError("Review notes are required for warnings/corrections")
            if decision == "approved":
                values = dict(row["original_values"])
            if not valid_values(values):
                raise ValueError("Invalid corrected values")
            if decision == "approved" and values != row["original_values"]:
                raise ValueError("Corrections must use 'Correct & approve'")
        if decision == "rejected" and not notes:
            raise ValueError("Rejection reason is required")
        row.update({
            "decision": decision,
            "engineering_approval": decision in {"approved", "corrected_and_approved"},
            "reviewed_values": values if decision in {"approved", "corrected_and_approved"} else None,
            "reviewer": reviewer or None,
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
        })
        self.persist()
        return row


def _valid_evidence_for_paths(validation: dict, unified: dict, unified_path: Path) -> bool:
    source = validation.get("source_report")
    if not source or Path(source).resolve() != unified_path.resolve():
        return False
    if validation.get("document") != unified.get("document") or not unified.get("document"):
        return False
    try:
        return datetime.fromisoformat(validation["validated_at_utc"]) >= datetime.fromisoformat(unified["run_utc"])
    except (KeyError, TypeError, ValueError):
        return False


def valid_values(values) -> bool:
    if not isinstance(values, dict):
        return False
    if set(values) != {name for name, _ in FIELDS}:
        return False
    if not isinstance(values["geometric_symbol"], str) or not values["geometric_symbol"].strip():
        return False
    try:
        n = Decimal(str(values["tolerance"]).replace(",", "."))
        if not n.is_finite() or n < 0:
            return False
    except (InvalidOperation, TypeError, ValueError):
        return False
    for name in ("diameter_modifier", "material_condition_modifier"):
        v = values[name]
        if v is not None and (not isinstance(v, str) or not v.strip()):
            return False
    return isinstance(values["datum_references"], list) and all(
        isinstance(d, str) and bool(d.strip()) for d in values["datum_references"]
    )


def make_button(parent, text, command, *, color=ACCENT, fg=BG, width=None):
    btn = tk.Button(
        parent, text=text, command=command, bg=color, fg=fg,
        activebackground=color, activeforeground=fg,
        font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
        cursor="hand2", padx=18, pady=11, highlightthickness=0,
    )
    if width is not None:
        btn.configure(width=width)
    return btn


def label(parent, text, size=10, color=TEXT, bold=False, **kwargs):
    return tk.Label(
        parent, text=text, bg=parent.cget("bg"), fg=color,
        font=("Segoe UI", size, "bold" if bold else "normal"),
        anchor="w", **kwargs,
    )


def card(parent, **kwargs):
    return tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1, **kwargs)


class DesktopApp:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("CATIA Engineering Extractor | Studio")
        self.window.geometry("1160x800")
        self.window.minsize(1020, 720)
        self.window.configure(bg=BG)
        self.store = ReviewStore()
        self.events = queue.Queue()
        self.busy = False
        self.index = 0
        self.image_ref = None
        self.current_review_image = None
        self._review_source_image = None
        self._image_redraw_job = None
        self.current_page = "extract"
        self.review_inputs = {}
        self.export_format = tk.StringVar(value="excel")
        self.reviewer_var = tk.StringVar()
        self.state_text = tk.StringVar(value="Prêt à démarrer")
        self.document_text = tk.StringVar(value="Aucune pièce analysée")
        self.stage_states = ["waiting"] * 6
        self._layout()
        self.show_page("extract")
        self.window.after(120, self._drain_events)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if self.busy:
            messagebox.showwarning("Traitement en cours", "Terminez le traitement avant de fermer la fenêtre.")
            return
        self.window.destroy()

    def _layout(self):
        sidebar = tk.Frame(self.window, bg=SIDE, width=235)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="◈  CATIA STUDIO", fg=TEXT, bg=SIDE,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=23, pady=(30, 7))
        tk.Label(sidebar, text="ENGINEERING EXTRACTOR  /  V1", fg=MUTED,
                 bg=SIDE, font=("Segoe UI", 8)).pack(anchor="w", padx=24, pady=(0, 47))
        self.nav_buttons = {}
        for title, key in (("01  Extraction", "extract"), ("02  Human Review", "review"),
                           ("03  Export Center", "export")):
            btn = tk.Button(sidebar, text=title, anchor="w", relief="flat", bd=0,
                            bg=SIDE, fg=MUTED, activebackground=CARD2,
                            activeforeground=TEXT, font=("Segoe UI", 11),
                            padx=24, pady=17, cursor="hand2",
                            command=lambda k=key: self.show_page(k))
            btn.pack(fill="x", pady=2)
            self.nav_buttons[key] = btn
        tk.Label(sidebar, text="LOCAL PROCESSING\nCATIA V5  •  WINDOWS",
                 justify="left", fg="#63809D", bg=SIDE,
                 font=("Segoe UI", 9)).pack(side="bottom", anchor="w", padx=24, pady=26)

        right = tk.Frame(self.window, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        header = tk.Frame(right, bg=BG)
        header.pack(fill="x", padx=32, pady=(24, 20))
        label(header, "ENGINEERING CONTROL CENTER", 9, MUTED, True).pack(anchor="w")
        label(header, "CATIA Data Extraction", 23, TEXT, True).pack(anchor="w", pady=(4, 5))
        tk.Label(header, textvariable=self.document_text, fg=MUTED, bg=BG,
                 font=("Segoe UI", 10)).pack(anchor="w")
        status = tk.Frame(header, bg=BG)
        status.place(relx=1, x=-2, y=8, anchor="ne")
        tk.Label(status, text="●", fg=ACCENT, bg=BG, font=("Segoe UI", 13)).pack(side="left", padx=(0, 7))
        tk.Label(status, textvariable=self.state_text, fg=TEXT, bg=BG,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self.container = tk.Frame(right, bg=BG)
        self.container.pack(fill="both", expand=True, padx=30, pady=(0, 25))
        self.pages = {x: tk.Frame(self.container, bg=BG) for x in ("extract", "review", "export")}
        self._build_extract()
        self._build_review()
        self._build_export()

    def show_page(self, page):
        self.current_page = page
        for key, frame in self.pages.items():
            if key == page:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
            self.nav_buttons[key].configure(bg=CARD2 if key == page else SIDE,
                                            fg=TEXT if key == page else MUTED)

    def _build_extract(self):
        page = self.pages["extract"]
        hero = card(page)
        hero.pack(fill="x", pady=(0, 17))
        inner = tk.Frame(hero, bg=CARD)
        inner.pack(fill="x", padx=23, pady=20)
        label(inner, "01  /  EXTRACTION PIPELINE", 9, ACCENT, True).pack(anchor="w")
        label(inner, "De CATIA à des données structurées", 16, TEXT, True).pack(anchor="w", pady=(5, 6))
        label(inner, "Ouvrez votre CATPart dans CATIA V5, puis lancez l'extraction.\n"
                     "L'application se minimise durant les captures pour ne pas masquer CATIA.",
              10, MUTED).pack(anchor="w", pady=(0, 14))
        actions = tk.Frame(inner, bg=CARD)
        actions.pack(anchor="w")
        self.start_button = make_button(actions, "▶  Start Extraction", self.start_extraction)
        self.start_button.pack(side="left", padx=(0, 10))
        make_button(actions, "Charger dernier rapport", self.load_existing,
                    color=CARD2, fg=TEXT).pack(side="left")

        progress = card(page)
        progress.pack(fill="x", pady=(0, 17))
        self.stage_labels = []
        steps = ["CATIA COM + GAP", "VISION / FULL FRAME", "GD&T OCR",
                 "UNIFIED REPORT", "ENGINEERING VALIDATION", "HUMAN REVIEW"]
        for i, step in enumerate(steps):
            grid_r, grid_c = divmod(i, 2)
            tile = tk.Frame(progress, bg=CARD)
            tile.grid(row=grid_r, column=grid_c, sticky="ew", padx=20, pady=10)
            dot = tk.Label(tile, text="○", bg=CARD, fg=MUTED, font=("Segoe UI", 14))
            dot.pack(side="left", padx=(0, 9))
            item = label(tile, step, 10, TEXT, True)
            item.pack(side="left")
            self.stage_labels.append((dot, item))
        progress.grid_columnconfigure(0, weight=1)
        progress.grid_columnconfigure(1, weight=1)
        self._update_stages()

        logcard = card(page)
        logcard.pack(fill="both", expand=True)
        top = tk.Frame(logcard, bg=CARD)
        top.pack(fill="x", padx=18, pady=(14, 9))
        label(top, "LIVE PIPELINE LOG", 9, MUTED, True).pack(side="left")
        make_button(top, "Effacer", lambda: self.log.delete("1.0", "end"),
                    color=CARD2, fg=MUTED).pack(side="right")
        self.log = tk.Text(logcard, bg=FIELD, fg="#D4E1F1", relief="flat", bd=0,
                           insertbackground=TEXT, state="normal", font=("Consolas", 9),
                           padx=13, pady=12, highlightthickness=0, wrap="word")
        self.log.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self._log("Prêt. Ouvrez une pièce dans CATIA V5 avant de démarrer.")

    def _build_review(self):
        page = self.pages["review"]
        # A scrolling work area keeps all review controls accessible even on
        # laptops using Windows 125%-150% display scaling.
        scroll = tk.Frame(page, bg=BG)
        scroll.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll, bg=BG, highlightthickness=0, bd=0)
        bar = tk.Scrollbar(scroll, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        page = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=page, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        page.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        def scroll_wheel(event):
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<Enter>", lambda event: canvas.bind_all("<MouseWheel>", scroll_wheel))
        canvas.bind("<Leave>", lambda event: canvas.unbind_all("<MouseWheel>"))
        self.review_canvas = canvas
        heading = card(page)
        heading.pack(fill="x", pady=(0, 15))
        upper = tk.Frame(heading, bg=CARD)
        upper.pack(fill="x", padx=20, pady=16)
        label(upper, "02  /  HUMAN ENGINEERING VERIFICATION", 9, ACCENT, True).pack(anchor="w")
        self.review_title = label(upper, "Aucun rapport chargé", 15, TEXT, True)
        self.review_title.pack(anchor="w", pady=(5, 6))
        self.review_status = label(upper, "Lancez l'extraction ou chargez un rapport existant.", 10, MUTED)
        self.review_status.pack(anchor="w")
        nav = tk.Frame(upper, bg=CARD)
        nav.pack(fill="x", pady=(13, 0))
        make_button(nav, "‹ Précédent", lambda: self.move_review(-1),
                    color=CARD2, fg=TEXT).pack(side="left", padx=(0, 9))
        make_button(nav, "Suivant ›", lambda: self.move_review(1),
                    color=CARD2, fg=TEXT).pack(side="left")
        self.review_count = label(nav, "0 / 0", 10, MUTED)
        self.review_count.pack(side="right")

        imagecard = card(page)
        imagecard.pack(fill="x", pady=(0, 13))
        image_header = tk.Frame(imagecard, bg=CARD)
        image_header.pack(fill="x", padx=18, pady=(13, 0))
        label(image_header, "GD&T  /  FULL FRAME", 9, MUTED, True).pack(side="left")
        make_button(image_header, "Ouvrir l'image originale",
                    self._open_original_image, color=CARD2, fg=TEXT).pack(side="right")

        # Canvas avoids the layout/pixelation issues caused by Tk PhotoImage.zoom.
        # Keep a fixed height: changing it from <Configure> causes redraw loops.
        self.image_canvas = tk.Canvas(
            imagecard, bg=FIELD, highlightthickness=0, bd=0,
            height=245, cursor="hand2",
        )
        self.image_canvas.pack(fill="x", padx=14, pady=(11, 5))
        self.image_canvas.bind("<Configure>", self._schedule_review_image_redraw)
        self.image_canvas.bind("<Double-Button-1>", lambda _event: self._open_original_image())
        self.image_info = label(imagecard, "Aucune image chargée", 9, MUTED)
        self.image_info.pack(anchor="w", padx=18, pady=(0, 12))

        editcard = card(page)
        editcard.pack(fill="both", expand=True)
        body = tk.Frame(editcard, bg=CARD)
        body.pack(fill="x", padx=18, pady=13)
        self.review_warnings = label(body, "", 9, AMBER, wraplength=710, justify="left")
        self.review_warnings.pack(anchor="w", pady=(0, 9))
        self.inputs_frame = tk.Frame(body, bg=CARD)
        self.inputs_frame.pack(fill="x")
        for i, (key, title) in enumerate(FIELDS):
            row, col = divmod(i, 2)
            cell = tk.Frame(self.inputs_frame, bg=CARD)
            cell.grid(row=row, column=col, sticky="ew", padx=(0, 15), pady=5)
            label(cell, title, 9, MUTED).pack(anchor="w", pady=(0, 4))
            var = tk.StringVar()
            entry = tk.Entry(cell, textvariable=var, relief="flat", bg=FIELD, fg=TEXT,
                             insertbackground=TEXT, highlightthickness=1,
                             highlightbackground=LINE, highlightcolor=ACCENT,
                             font=("Segoe UI", 11))
            entry.pack(fill="x", ipady=7)
            self.review_inputs[key] = var
        self.inputs_frame.grid_columnconfigure(0, weight=1)
        self.inputs_frame.grid_columnconfigure(1, weight=1)
        footer = tk.Frame(editcard, bg=CARD)
        footer.pack(fill="x", padx=18, pady=(0, 14))
        label(footer, "Reviewer name / ID", 9, MUTED).grid(row=0, column=0, sticky="w")
        label(footer, "Review notes / rejection reason", 9, MUTED).grid(row=0, column=1, sticky="w")
        self.reviewer_entry = tk.Entry(footer, textvariable=self.reviewer_var, bg=FIELD, fg=TEXT,
                                       insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
        self.reviewer_entry.grid(row=1, column=0, sticky="ew", ipady=8, padx=(0, 12), pady=(4, 13))
        self.notes_entry = tk.Entry(footer, bg=FIELD, fg=TEXT, insertbackground=TEXT,
                                    relief="flat", font=("Segoe UI", 10))
        self.notes_entry.grid(row=1, column=1, sticky="ew", ipady=8, pady=(4, 13))
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=2)
        actions = tk.Frame(footer, bg=CARD)
        actions.grid(row=2, column=0, columnspan=2, sticky="w")
        self.review_buttons = []
        for title, decision, color, fg in (
            ("✓  Approuver", "approved", ACCENT, BG),
            ("✎  Corriger & approuver", "corrected_and_approved", BLUE, BG),
            ("✕  Rejeter", "rejected", RED, BG),
            ("→  Passer", "pending", CARD2, TEXT),
        ):
            btn = make_button(actions, title, lambda x=decision: self.save_review(x),
                              color=color, fg=fg)
            btn.pack(side="left", padx=(0, 9))
            self.review_buttons.append(btn)
        label(editcard, "Approbation jamais automatique · les annotations en attente restent exportables avec leur statut.",
              9, MUTED).pack(anchor="w", padx=18, pady=(0, 11))

    def _build_export(self):
        page = self.pages["export"]
        panel = card(page)
        panel.pack(fill="x", pady=(0, 18))
        inner = tk.Frame(panel, bg=CARD)
        inner.pack(fill="x", padx=26, pady=24)
        label(inner, "03  /  EXPORT CENTER", 9, ACCENT, True).pack(anchor="w")
        label(inner, "Télécharger votre rapport", 19, TEXT, True).pack(anchor="w", pady=(7, 7))
        label(inner, "Tous les exports incluent les données COM + Vision + OCR et la trace des validations.\n"
                     "Sans approbation humaine, les mesures restent provisoires (non approuvées).",
              10, MUTED).pack(anchor="w", pady=(0, 22))
        for key, title, description in (
            ("excel", "Excel  .xlsx", "Classeur de 17 onglets · COM / OCR / validation / review"),
            ("csv", "CSV  .zip", "17 fichiers CSV rassemblés dans un ZIP"),
            ("json", "JSON  .json", "Toutes les données, y compris les rapports bruts non abrégés"),
        ):
            line = tk.Frame(inner, bg=CARD2)
            line.pack(fill="x", pady=5)
            rb = tk.Radiobutton(line, variable=self.export_format, value=key,
                                text=title, bg=CARD2, fg=TEXT, activebackground=CARD2,
                                activeforeground=TEXT, selectcolor=FIELD,
                                font=("Segoe UI", 11, "bold"), cursor="hand2")
            rb.pack(anchor="w", padx=14, pady=(11, 0))
            label(line, description, 9, MUTED).pack(anchor="w", padx=38, pady=(0, 11))
        self.download_button = make_button(inner, "↓  Télécharger", self.export_selected)
        self.download_button.pack(anchor="w", pady=(23, 5))
        self.export_summary = label(inner, "Analyse requise avant export.", 10, MUTED)
        self.export_summary.pack(anchor="w", pady=(7, 0))

    def _update_stages(self):
        mapping = {"waiting": ("○", MUTED), "running": ("◌", AMBER),
                   "done": ("●", ACCENT), "review": ("●", BLUE), "error": ("×", RED)}
        for (dot, item), status in zip(self.stage_labels, self.stage_states):
            mark, color = mapping[status]
            dot.config(text=mark, fg=color)
            item.config(fg=TEXT if status != "waiting" else MUTED)

    def _log(self, text):
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")

    def _stage(self, i, status="running"):
        if status == "running":
            for j in range(i):
                self.stage_states[j] = "done"
        self.stage_states[i] = status
        self._update_stages()

    def _check_log_stage(self, line):
        stages = (("[1/4]", 0), ("[1/5]", 0), ("[2/4]", 1), ("[2/5]", 1),
                  ("[3/4]", 2), ("[3/5]", 2), ("[4/4]", 3), ("[4/5]", 3),
                  ("[5/5]", 4))
        for prefix, index in stages:
            if prefix in line:
                self._stage(index)
                break

    def start_extraction(self):
        if self.busy:
            return
        if not messagebox.askyesno(
            "CATIA V5 - Préparation",
            "Votre pièce .CATPart est-elle ouverte dans CATIA V5 ?\n\n"
            "Cliquez Oui pour lancer COM → Vision → OCR → Validation.\n"
            "La fenêtre sera réduite pendant les captures.",
        ):
            return
        self.busy = True
        self.start_button.config(state="disabled")
        self.download_button.config(state="disabled")
        self.state_text.set("Extraction en cours…")
        self.stage_states = ["waiting"] * 6
        self._stage(0)
        self._log("===== NEW CATIA SESSION =====")
        self.show_page("extract")
        self.window.iconify()  # Keep CATIA captures clear of this window.
        threading.Thread(target=self._extract_worker, daemon=True).start()

    def _run_cli(self, module, started_ns=None):
        env = os.environ.copy()
        src = str(ROOT / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        command = [sys.executable, "-u", "-m", module]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(command, cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                bufsize=1, **kwargs)
        assert proc.stdout is not None
        for output in proc.stdout:
            self.events.put(("log", output.rstrip()))
        code = proc.wait()
        if code:
            raise RuntimeError(f"{module} returned exit code {code}. See pipeline log.")

    def _extract_worker(self):
        try:
            started_ns = time.time_ns()
            self._run_cli("catia_extractor.pipeline_unified.runner")
            # Some Unified Runner builds already run validation. Don't do it twice.
            fresh = (VALIDATION.is_file()
                     and VALIDATION.stat().st_mtime_ns >= started_ns)
            if not fresh:
                self.events.put(("stage", 4))
                self._run_cli("catia_extractor.pipeline_unified.engineering_validator")
            self.events.put(("extraction_complete", None))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def load_existing(self):
        if self.busy:
            return
        try:
            self._load_review()
        except Exception as exc:
            messagebox.showerror("Impossible de charger", str(exc))

    def _load_review(self):
        report = self.store.prepare()
        self.index = 0
        self.document_text.set(f"Document : {report.get('document', 'N/A')}")
        self.state_text.set("Revue humaine disponible")
        self.stage_states = ["done"] * 5 + ["review"]
        self._update_stages()
        self.show_review()
        self._refresh_export_summary()
        self.show_page("review")

    def _drain_events(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "log":
                    self._log(value)
                    self._check_log_stage(value)
                elif event == "stage":
                    self._stage(value)
                elif event == "error":
                    self.busy = False
                    self.start_button.config(state="normal")
                    self.download_button.config(state="normal")
                    self.state_text.set("Erreur : consulter le log")
                    self.window.deiconify()
                    self.window.lift()
                    self._log("ERROR: " + value)
                    self.stage_states[max((i for i,s in enumerate(self.stage_states) if s == "running"), default=0)] = "error"
                    self._update_stages()
                    messagebox.showerror("Extraction interrompue", value)
                elif event == "extraction_complete":
                    self.busy = False
                    self.start_button.config(state="normal")
                    self.download_button.config(state="normal")
                    self.window.deiconify()
                    self.window.lift()
                    try:
                        self._load_review()
                        self._log("Extraction terminée. Human Review disponible.")
                    except Exception as exc:
                        self.state_text.set("Vérification à corriger")
                        self._log("Review preparation error: " + str(exc))
                        messagebox.showerror("Human Review non disponible", str(exc))
                elif event == "export_complete":
                    self.busy = False
                    self.start_button.config(state="normal")
                    self.download_button.config(state="normal")
                    self.state_text.set("Export terminé")
                    messagebox.showinfo("Téléchargement terminé", f"Fichier enregistré :\n{value}")
                    self._refresh_export_summary()
                elif event == "export_error":
                    self.busy = False
                    self.start_button.config(state="normal")
                    self.download_button.config(state="normal")
                    self.state_text.set("Erreur d'export")
                    messagebox.showerror("Erreur d'export", value)
        except queue.Empty:
            pass
        self.window.after(120, self._drain_events)

    def show_review(self):
        self.review_canvas.yview_moveto(0)
        rows = (self.store.report or {}).get("results", [])
        if not rows:
            self.review_title.config(text="Aucune annotation à revoir")
            self.review_status.config(text="Vous pouvez exporter les données COM disponibles.")
            self._show_image(None)
            self.review_count.config(text="0 / 0")
            return
        self.index = max(0, min(self.index, len(rows)-1))
        row = rows[self.index]
        self.review_title.config(text=row.get("annotation_name") or row["annotation_id"])
        self.review_status.config(text=f"Validation: {row['validation_status']}     |     Decision: {row['decision']}")
        self.review_count.config(text=f"{self.index + 1} / {len(rows)}")
        issues = row.get("issues", [])
        self.review_warnings.config(text=("  •  ".join(
            f"{issue.get('code')}: {issue.get('detail')}" for issue in issues
        ) if issues else "Aucune alerte automatique."),
                                    fg=AMBER if issues else ACCENT)
        values = row.get("reviewed_values") or row.get("original_values") or {}
        for key, _ in FIELDS:
            val = values.get(key)
            self.review_inputs[key].set(",".join(val) if isinstance(val, list)
                                        else "" if val is None else str(val))
        self.notes_entry.delete(0, "end")
        self.notes_entry.insert(0, row.get("notes") or "")
        if row.get("reviewer") and not self.reviewer_var.get():
            self.reviewer_var.set(row["reviewer"])
        self._show_image(row.get("review_image"))

    def _preview_message(self, message):
        self.image_ref = None
        self.image_canvas.delete("all")
        width = max(300, self.image_canvas.winfo_width())
        height = max(150, self.image_canvas.winfo_height())
        self.image_canvas.create_text(
            width // 2, height // 2, text=message,
            fill=MUTED, font=("Segoe UI", 11),
            width=max(200, width - 50), justify="center",
        )
        self.image_info.config(text="Aperçu indisponible")

    def _schedule_review_image_redraw(self, _event=None):
        # Coalesce rapid resize events to avoid flicker and excessive PIL work.
        if self._image_redraw_job is None:
            self._image_redraw_job = self.window.after_idle(self._render_review_image)

    def _show_image(self, path_text):
        # Reload the source when moving between annotations, including after a
        # new extraction that may overwrite an existing full_frame.png.
        self.current_review_image = path_text
        self._review_source_image = None
        self._schedule_review_image_redraw()

    def _render_review_image(self):
        self._image_redraw_job = None
        path_text = self.current_review_image
        canvas_width = self.image_canvas.winfo_width()
        canvas_height = self.image_canvas.winfo_height()

        if canvas_width < 30 or canvas_height < 30:
            return  # The <Configure> event will render once laid out.
        if not path_text:
            self._preview_message("Aucune image GD&T chargée")
            return
        path = Path(path_text)
        if not path.is_file():
            self._preview_message("Image manquante : vérifiez le rapport de validation")
            return
        if Image is None or ImageTk is None:
            self._preview_message("Installez Pillow : python -m pip install pillow")
            return

        try:
            if self._review_source_image is None:
                # Convert to RGB to avoid alpha/transparency mishandling.
                with Image.open(path) as source:
                    self._review_source_image = source.convert("RGB")
            source = self._review_source_image
            margin = 24
            available_w = max(1, canvas_width - margin * 2)
            available_h = max(1, canvas_height - margin * 2)
            factor = min(available_w / source.width, available_h / source.height)
            factor = max(factor, 0.01)
            dest_w = max(1, round(source.width * factor))
            dest_h = max(1, round(source.height * factor))

            # CAD glyphs benefit from high-quality scaling while preserving
            # the original aspect ratio and keeping the full frame visible.
            interpolation = Image.Resampling.LANCZOS
            scaled = source.resize((dest_w, dest_h), interpolation)
            photo = ImageTk.PhotoImage(scaled, master=self.window)
            self.image_ref = photo  # Without this reference, Tk shows nothing.
            self.image_canvas.delete("all")
            self.image_canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                anchor="center", image=photo,
            )
            self.image_info.config(
                text=f"Source : {source.width} × {source.height} px   •   "
                     f"Affichage : {dest_w} × {dest_h} px   •   "
                     "Double-clic : ouvrir l'original"
            )
        except Exception as exc:
            self._preview_message(f"Impossible d'afficher l'image : {exc}")

    def _open_original_image(self):
        path_text = self.current_review_image
        if not path_text or not Path(path_text).is_file():
            messagebox.showwarning("Image manquante", "Aucune image GD&T disponible.")
            return
        try:
            if os.name == "nt":
                os.startfile(str(Path(path_text)))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(Path(path_text))])
            else:
                subprocess.Popen(["xdg-open", str(Path(path_text))])
        except Exception as exc:
            messagebox.showerror("Ouverture impossible", str(exc))

    def move_review(self, shift):
        rows = (self.store.report or {}).get("results", [])
        if rows:
            self.index = (self.index + shift) % len(rows)
            self.show_review()

    def _get_corrections(self):
        values = {}
        for key, _ in FIELDS:
            text = self.review_inputs[key].get().strip()
            if key == "datum_references":
                values[key] = [v.strip().upper() for v in text.split(",") if v.strip()]
            elif key in {"diameter_modifier", "material_condition_modifier"}:
                values[key] = text or None
            elif key == "tolerance":
                values[key] = text.replace(",", ".")
            else:
                values[key] = text
        return values

    def save_review(self, decision):
        if self.busy or not self.store.report or not self.store.report["results"]:
            return
        reviewer = self.reviewer_var.get().strip()
        notes = self.notes_entry.get().strip()
        if decision in {"approved", "corrected_and_approved"}:
            question = ("Vous confirmez avoir vérifié la pièce / l'image CATIA, "
                        "et signez cette annotation ?")
            if not messagebox.askyesno("Confirmation de l'ingénieur", question):
                return
        elif decision == "rejected":
            if not messagebox.askyesno("Rejeter l'annotation", "Confirmer le rejet ?"):
                return
        try:
            values = self._get_corrections() if decision == "corrected_and_approved" else None
            self.store.decide(self.index, decision, reviewer, notes, values)
        except Exception as exc:
            messagebox.showwarning("Décision non enregistrée", str(exc))
            return
        self.show_review()
        self._refresh_export_summary()
        if decision in {"approved", "corrected_and_approved", "rejected", "pending"}:
            rows = self.store.report["results"]
            if self.index < len(rows)-1:
                self.index += 1
                self.show_review()
            else:
                messagebox.showinfo("Revue enregistrée", "Toutes les annotations peuvent être exportées.\n"
                                    "Les décisions Pending restent non approuvées.")
                self.show_page("export")

    def _refresh_export_summary(self):
        summary = (self.store.report or {}).get("summary", {})
        n = summary.get("annotations", 0)
        good = summary.get("approved", 0) + summary.get("corrected_and_approved", 0)
        pending = n - good
        self.export_summary.configure(text=(
            f"Pièce: {(self.store.report or {}).get('document', '—')}   •   "
            f"Approuvées: {good}/{n}   •   Sans approbation: {pending}"
        ))

    def export_selected(self):
        if self.busy:
            return
        if not (self.store.report and UNIFIED.is_file()):
            messagebox.showwarning("Rapport manquant", "Lancez l'extraction ou chargez un rapport existant.")
            return
        kind = self.export_format.get()
        ext = {"excel": ".xlsx", "csv": ".zip", "json": ".json"}[kind]
        types = {"excel": [("Excel workbook", "*.xlsx")],
                 "csv": [("ZIP de fichiers CSV", "*.zip")],
                 "json": [("JSON", "*.json")]}[kind]
        name = f"{Path(str(self.store.report.get('document') or 'CATIA')).stem}_engineering{ext}"
        target = filedialog.asksaveasfilename(title="Télécharger le rapport", initialfile=name,
                                               defaultextension=ext, filetypes=types)
        if not target:
            return
        self.busy = True
        self.start_button.config(state="disabled")
        self.download_button.config(state="disabled")
        self.state_text.set("Préparation du fichier…")
        threading.Thread(target=self._export_worker, args=(kind, Path(target)), daemon=True).start()

    def _export_worker(self, kind: str, target: Path):
        try:
            from catia_extractor.pipeline_unified.final_report import run as finalize
            from catia_extractor.pipeline_unified.export_engineering import run as export_all
            final = finalize(project_root=ROOT)
            output = export_all(project_root=ROOT)
            if kind == "excel":
                src = output.get("excel")
                if not src or not Path(src).is_file():
                    raise RuntimeError("Excel non généré. Vérifiez l'installation d'openpyxl.")
                source = Path(src)
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
            elif kind == "json":
                source = Path(output["json"])
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
            else:
                csv_paths = output.get("csv", {})
                if not csv_paths:
                    raise RuntimeError("No CSV files generated")
                with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
                    for sheet, file_path in csv_paths.items():
                        path = Path(file_path)
                        if not path.is_file():
                            raise FileNotFoundError(path)
                        zipf.write(path, arcname=path.name)
            self.events.put(("export_complete", str(target)))
        except Exception as exc:
            self.events.put(("export_error", str(exc)))

    def run(self):
        self.window.mainloop()


def main():
    DesktopApp().run()


if __name__ == "__main__":
    main()
