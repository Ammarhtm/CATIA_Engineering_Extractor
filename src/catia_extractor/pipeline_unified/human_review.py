"""Manual CATIA GD&T review; never modifies COM, vision, or OCR reports.

Run from project root:
    python -m catia_extractor.pipeline_unified.human_review
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPROVED = {"approved", "corrected_and_approved"}
FIELDS = (
    "geometric_symbol", "tolerance", "diameter_modifier",
    "material_condition_modifier", "datum_references",
)


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _save(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _hash_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _fingerprint(record: dict, source_run: str, image_hash: str | None) -> str:
    # The decision expires after a new run, different validation data, or changed image.
    content = {
        "run": source_run,
        "record": record,
        "image_sha256": image_hash,
    }
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _ask(message: str) -> str:
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nReview interrupted; previous decisions remain saved.")
        raise SystemExit(1)


def _required(message: str) -> str:
    while True:
        response = _ask(message)
        if response:
            return response
        print("This field is required.")


def _correct(original: dict) -> dict:
    values = dict(original)
    values["datum_references"] = list(original.get("datum_references") or [])
    print("  Enter = keep current value; '-' = remove optional value")

    for field in FIELDS:
        previous = values.get(field)
        previous_label = ",".join(previous) if isinstance(previous, list) else str(previous)
        while True:
            text = _ask(f"  {field} [{previous_label}]: ")
            if not text:
                break

            if field == "datum_references":
                datums = [] if text == "-" else [s.strip().upper() for s in text.split(",")]
                if any(not datum or not datum.isalnum() for datum in datums):
                    print("Use comma-separated datum names, e.g. A,B,C or '-' to remove.")
                    continue
                values[field] = datums
                break

            if field in {"diameter_modifier", "material_condition_modifier"}:
                values[field] = None if text == "-" else text
                break

            if field == "tolerance":
                try:
                    number = Decimal(text.replace(",", "."))
                    if not number.is_finite() or number < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    print("Tolerance must be a non-negative number (e.g. 0.02).")
                    continue
                values[field] = text.replace(",", ".")
                break

            if field == "geometric_symbol":
                if text == "-":
                    print("Geometric symbol cannot be removed during approval.")
                    continue
                values[field] = text
                break

    return values


def _open_image(image: Path) -> None:
    if not image.is_file():
        print(f"Image missing: {image}")
        return
    if os.name == "nt":
        try:
            os.startfile(str(image))  # type: ignore[attr-defined]
        except OSError as exc:
            print(f"Cannot open image automatically: {exc}")
            print(f"Open manually: {image}")
    else:
        print(f"Open manually: {image}")


def _summary(report: dict) -> None:
    rows = report["results"]
    report["summary"] = {
        "annotations": len(rows),
        "approved": sum(r["decision"] == "approved" for r in rows),
        "corrected_and_approved": sum(r["decision"] == "corrected_and_approved" for r in rows),
        "rejected": sum(r["decision"] == "rejected" for r in rows),
        "pending": sum(r["decision"] == "pending" for r in rows),
        "correction_pending_approval": sum(
            r["decision"] == "correction_pending_approval" for r in rows
        ),
    }
    report["engineering_approval"] = bool(rows) and all(
        r["decision"] in APPROVED and r["engineering_approval"] is True
        for r in rows
    )
    report["reviewed_at_utc"] = datetime.now(timezone.utc).isoformat()


def run(project_root=None) -> dict:
    root = Path(project_root).resolve() if project_root else ROOT
    base = root / "output" / "pipeline_unified"
    validation_path = base / "validation_report.json"
    output_path = base / "human_review_report.json"
    if not validation_path.is_file():
        raise FileNotFoundError(f"Run engineering_validator first: {validation_path}")

    validation = _load(validation_path)
    unified_path = base / "engineering_report.json"
    unified = _load(unified_path) if unified_path.is_file() else {}
    if unified and unified.get("document") != validation.get("document"):
        raise ValueError("Unified and validation reports refer to different documents")
    if unified.get("run_utc") and validation.get("validated_at_utc"):
        try:
            run_time = datetime.fromisoformat(unified["run_utc"])
            validation_time = datetime.fromisoformat(validation["validated_at_utc"])
        except ValueError as exc:
            raise ValueError("Invalid timestamp in source reports") from exc
        if validation_time < run_time:
            raise ValueError("Validation is older than the latest unified run; rerun validator")
    source_run = unified.get("run_utc") or validation.get("validated_at_utc") or "unknown"

    previous = _load(output_path) if output_path.is_file() else {}
    old_by_id = {r["annotation_id"]: r for r in previous.get("results", [])}
    rows, ids = [], set()
    for record in validation.get("results", []):
        key = record.get("annotation_id")
        if not key or key in ids:
            raise ValueError(f"Missing or duplicate annotation_id: {key!r}")
        ids.add(key)
        image = Path(record.get("review_image") or "")
        digest = _hash_file(image)
        fingerprint = _fingerprint(record, source_run, digest)
        old = old_by_id.get(key, {})
        current = old.get("evidence_fingerprint") == fingerprint
        # Preserve a previous decision only when ALL evidence is unchanged.
        saved = old if current else {}
        rows.append({
            "annotation_id": key,
            "annotation_name": record.get("annotation_name"),
            "validation_status": record.get("status"),
            "issues": record.get("issues", []),
            "review_image": str(image),
            "image_sha256": digest,
            "evidence_fingerprint": fingerprint,
            "original_values": record.get("extracted_values", {}),
            "reviewed_values": saved.get("reviewed_values"),
            "decision": saved.get("decision", "pending"),
            "engineering_approval": saved.get("engineering_approval", False),
            "reviewer": saved.get("reviewer"),
            "reviewed_at_utc": saved.get("reviewed_at_utc"),
            "notes": saved.get("notes", ""),
            "previous_evidence_changed": bool(old) and not current,
        })

    report = {
        "review_version": "human-review-v1",
        "document": validation.get("document"),
        "source_run_utc": source_run,
        "source_validation_report": str(validation_path),
        "engineering_approval": False,
        "results": rows,
    }
    _summary(report)
    _save(output_path, report)  # Invalidates stale decisions immediately.

    if not rows:
        print("No annotation records available for review.")
        return report
    print("\n========== MANUAL ENGINEERING REVIEW ==========")
    reviewer = _required("Reviewer name / ID: ")

    for row in rows:
        print("\n" + "=" * 50)
        print("Annotation:", row["annotation_name"])
        print("Validation:", row["validation_status"])
        print("OCR values:", json.dumps(row["original_values"], ensure_ascii=False))
        print("Image:", row["review_image"])
        if row["previous_evidence_changed"]:
            print("WARNING: Evidence changed; previous sign-off was invalidated.")
        for issue in row["issues"]:
            print(f"  [{issue.get('severity')}] {issue.get('code')}: {issue.get('detail')}")
        print("Current decision:", row["decision"])

        while True:
            choice = _ask("[O]pen image  [A]pprove  [C]orrect  [R]eject  [S]kip: ").lower()
            if choice == "o":
                _open_image(Path(row["review_image"]))
                continue
            if choice in {"a", "c", "r", "s"}:
                break
            print("Choose O, A, C, R or S.")

        if choice == "s":
            continue
        if choice in {"a", "c"}:
            if row["validation_status"] == "blocked" or not row["image_sha256"]:
                print("Approval blocked: resolve validation blockers/image first.")
                continue
            values = dict(row["original_values"])
            if choice == "c":
                values = _correct(values)
                print("Final corrected values:", json.dumps(values, ensure_ascii=False))
            else:
                print("Values to approve:", json.dumps(values, ensure_ascii=False))
            notes = _ask("Review notes (required if warning/correction): ")
            if (choice == "c" or row["issues"]) and not notes:
                print("No notes: approval not saved. Review this item again.")
                continue
            confirmed = _ask("After checking the image/CATIA, type APPROVE to sign off: ")
            decision = (
                "corrected_and_approved" if choice == "c" else "approved"
            ) if confirmed == "APPROVE" else (
                "correction_pending_approval" if choice == "c" else "pending"
            )
            row.update({
                "decision": decision,
                "engineering_approval": decision in APPROVED,
                "reviewed_values": values if choice == "c" else values if decision in APPROVED else None,
                "reviewer": reviewer,
                "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
                "notes": notes,
            })
        else:
            reason = _required("Rejection reason: ")
            confirmed = _ask("Type REJECT to confirm: ")
            if confirmed != "REJECT":
                print("Rejection canceled.")
                continue
            row.update({
                "decision": "rejected",
                "engineering_approval": False,
                "reviewed_values": None,
                "reviewer": reviewer,
                "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
                "notes": reason,
            })

        _summary(report)
        _save(output_path, report)
        print("Saved:", row["decision"])

    _summary(report)
    _save(output_path, report)
    print("\n========== REVIEW SUMMARY ==========")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("Engineering approval:", report["engineering_approval"])
    print("Report:", output_path)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review extracted CATIA GD&T evidence")
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    run(project_root=args.project_root)
