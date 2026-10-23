"""Full CATIA engineering export: COM + Vision + OCR + human approval.

Run from project root:
    python -m catia_extractor.pipeline_unified.export_engineering

Outputs to output/engineering_export/:
    engineering_data.xlsx               (if artifact_tool is installed)
    engineering_export_complete.json    (lossless source reports)
    csv/*.csv                           (one CSV per data sheet)

No CATIA connection is required. No input JSON is modified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read_json(path: Path, *, required: bool = True) -> dict | None:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"Missing input report: {path}")
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        result = json.load(handle)
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return result


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def cell_value(value):
    """Keep numeric values numeric; escape spreadsheet-formula-like strings."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json_text(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return value
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value  # Mitigate CSV/Excel formula injection.
    return value


def record_rows(records, *, key_name: str | None = None) -> list[dict]:
    """Make a table from record dictionaries, preserving nested data as JSON."""
    rows = []
    for number, record in enumerate(records or [], start=1):
        if not isinstance(record, dict):
            record = {"value": record}
        row = {"row": number}
        if key_name is not None:
            row["source_family"] = key_name
        row.update(record)
        rows.append(row)
    return rows


def make_inventory(com: dict) -> list[dict]:
    rows = []
    for group in (com.get("tree_inventory") or {}).get("annotation_sets", []):
        set_name = (group.get("name") or {}).get("value")
        for annotation in group.get("annotations", []):
            props = annotation.get("properties") or {}
            row = {"annotation_set": set_name, "index": annotation.get("index")}
            for name, meta in props.items():
                if isinstance(meta, dict):
                    row[name] = meta.get("value")
                    if meta.get("status") != "success":
                        row[f"{name}_status"] = meta.get("status")
                        row[f"{name}_error"] = meta.get("error")
                else:
                    row[name] = meta
            row["original_record"] = annotation
            rows.append(row)
    return rows


def make_feature_tree(com: dict) -> list[dict]:
    rows = []
    for body in (com.get("feature_tree") or {}).get("bodies", []):
        body_name = (body.get("name") or {}).get("value")
        rows.append({"kind": "body", "body_name": body_name,
                     "shape_name": "", "type": "", "source": body})
        for shape in body.get("shapes", []):
            rows.append({
                "kind": "shape", "body_name": body_name,
                "shape_name": (shape.get("name") or {}).get("value"),
                "type": (shape.get("type") or {}).get("value"),
                "type_status": (shape.get("type") or {}).get("status"),
                "source": shape,
            })
    return rows


def make_approved_rows(final: dict) -> list[dict]:
    rows = []
    for record in final.get("results", []):
        values = record.get("final_values") or {}
        review = record.get("human_review") or {}
        status = record.get("approval_checks") or {}
        genuinely_approved = (
            record.get("engineering_approval") is True
            and status.get("passed") is True
            and bool(values)
        )
        rows.append({
            "annotation_id": record.get("annotation_id"),
            "annotation_name": record.get("annotation_name"),
            "approved": genuinely_approved,
            "decision": review.get("decision"),
            "geometric_symbol": values.get("geometric_symbol") if genuinely_approved else None,
            "tolerance": values.get("tolerance") if genuinely_approved else None,
            "diameter_modifier": values.get("diameter_modifier") if genuinely_approved else None,
            "material_condition": values.get("material_condition_modifier") if genuinely_approved else None,
            "datums": values.get("datum_references") if genuinely_approved else None,
            "reviewer": review.get("reviewer"),
            "reviewed_at_utc": review.get("reviewed_at_utc"),
            "image": (record.get("full_frame") or {}).get("image"),
            "approval_issues": status.get("issues"),
        })
    return rows


def make_ocr_rows(ocr: dict) -> list[dict]:
    rows = []
    for rec in ocr.get("results", []):
        symbol = rec.get("geometric_symbol") or {}
        tolerance = rec.get("tolerance") or {}
        rows.append({
            "annotation_id": rec.get("annotation_id"),
            "annotation_name": rec.get("annotation_name"),
            "status": rec.get("status"),
            "symbol": symbol.get("glyph"),
            "symbol_name": symbol.get("name"),
            "symbol_match_score": symbol.get("match_score"),
            "tolerance_raw": tolerance.get("raw"),
            "tolerance_value": tolerance.get("value"),
            "diameter_modifier": rec.get("diameter_modifier"),
            "material_condition": rec.get("material_condition_modifier"),
            "datums": rec.get("datum_references"),
            "raw_ocr": rec.get("raw_ocr"),
            "segmentation": rec.get("segmentation"),
            "warnings": rec.get("warnings"),
            "source_image": rec.get("source_image"),
        })
    return rows


def build_tables(com: dict, final: dict, reports: dict,
                 source_meta: list[dict]) -> dict[str, list[dict]]:
    extractors = com.get("extractor_results") or {}
    def family(name):
        entry = extractors.get(name) or {}
        return entry.get("data") or []

    pf = family("part_parameters_and_features")
    if not isinstance(pf, dict):
        pf = {}

    summary = [{
        "document": final.get("document"),
        "report_status": final.get("status"),
        "engineering_approval": final.get("engineering_approval"),
        "annotations_in_final": (final.get("summary") or {}).get("annotations"),
        "annotations_approved": (final.get("summary") or {}).get("approved"),
        "com_annotation_inventory": (com.get("tree_inventory") or {}).get("annotation_count"),
        "com_parameters": len(pf.get("parameters") or []),
        "com_features": len(pf.get("features") or []),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Approval covers final-report annotations only, not the entire COM inventory.",
    }]

    statuses = []
    for name, data in extractors.items():
        statuses.append({"family": name, "status": data.get("status"),
                         "count": data.get("count"), "error": data.get("error")})

    validation = reports.get("validation") or {}
    review = reports.get("human_review") or {}
    vision = reports.get("vision") or {}
    return {
        "Summary": summary,
        "COM Parameters": record_rows(pf.get("parameters")),
        "COM Features": record_rows(pf.get("features")),
        "Semantic GDT": record_rows(family("semantic_gdt")),
        "NonSemantic GDT": record_rows(family("nonsemantic_gdt")),
        "Dimensions": record_rows(family("dimensions")),
        "Datums": record_rows(family("datums")),
        "Reference Frames": record_rows(family("reference_frames")),
        "Annotation Inventory": make_inventory(com),
        "Feature Tree": make_feature_tree(com),
        "Extractor Status": statuses,
        "Approved GDT": make_approved_rows(final),
        "OCR Details": make_ocr_rows(reports.get("ocr") or {}),
        "Vision Details": record_rows([{
            "annotation_id": r.get("annotation_id"),
            "status": r.get("status"),
            "selected_seed": r.get("selected_seed"),
            "full_frame": r.get("full_frame"),
            "selection_confirmed": r.get("selection_confirmed"),
        } for r in vision.get("results", [])]),
        "Validation": record_rows([{
            "annotation_id": r.get("annotation_id"),
            "status": r.get("status"),
            "automatic_checks_passed": r.get("automatic_checks_passed"),
            "issues": r.get("issues"),
            "engineering_approval": r.get("engineering_approval"),
        } for r in validation.get("results", [])]),
        "Human Review": record_rows([{
            "annotation_id": r.get("annotation_id"),
            "decision": r.get("decision"),
            "reviewed_values": r.get("reviewed_values"),
            "reviewer": r.get("reviewer"),
            "reviewed_at_utc": r.get("reviewed_at_utc"),
            "notes": r.get("notes"),
            "evidence_fingerprint": r.get("evidence_fingerprint"),
        } for r in review.get("results", [])]),
        "Sources": source_meta,
    }


def table_matrix(records: list[dict]):
    columns = []
    for row in records:
        for field in row:
            if field not in columns:
                columns.append(field)
    if not columns:
        return [["no_data"]]
    return [columns] + [[cell_value(r.get(col)) for col in columns] for r in records]


def write_csv_tables(folder: Path, tables: dict) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    output = {}
    for sheet, rows in tables.items():
        path = folder / (sheet.lower().replace(" ", "_") + ".csv")
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(table_matrix(rows))
        output[sheet] = str(path)
    return output



def write_excel(path: Path, tables: dict) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    book = Workbook()
    book.remove(book.active)

    for name, records in tables.items():

        sheet = book.create_sheet(title=name)
        data = table_matrix(records)

        # Write data
        for row in data:
            cleaned_row = []

            for value in row:
                if isinstance(value, str):

                    # Remove characters unsupported by Excel
                    value = ILLEGAL_CHARACTERS_RE.sub("", value)

                    # Excel cell text limit
                    if len(value) > 32000:
                        value = (
                            value[:32000]
                            + " [see JSON bundle]"
                        )

                    # Prevent text being interpreted as a formula
                    if value.startswith("="):
                        value = "'" + value

                cleaned_row.append(value)

            sheet.append(cleaned_row)

        # Header formatting
        header_fill = PatternFill(
            fill_type="solid",
            fgColor="17324D"
        )

        header_font = Font(
            bold=True,
            color="FFFFFF",
            size=11
        )

        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True
            )

        sheet.row_dimensions[1].height = 28

        # Freeze first row
        sheet.freeze_panes = "A2"

        # Enable filters
        sheet.auto_filter.ref = sheet.dimensions

        # Column widths
        for col in range(1, sheet.max_column + 1):
            letter = get_column_letter(col)

            sheet.column_dimensions[letter].width = (
                29 if col == 1 else 23
            )

        # Body formatting
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True
                )

                if cell.row % 2 == 0:
                    cell.fill = PatternFill(
                        fill_type="solid",
                        fgColor="F1F5F9"
                    )

        print(f"Excel sheet created: {name}")

    # Save Excel
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    book.save(str(path))

    print(f"\nExcel successfully generated: {path}")



def run(project_root=None) -> dict:
    root = Path(project_root).resolve() if project_root else ROOT
    p1 = root / "output" / "pipeline_v1"
    p2 = root / "output" / "pipeline_v2"
    un = root / "output" / "pipeline_unified"
    destination = root / "output" / "engineering_export"
    destination.mkdir(parents=True, exist_ok=True)

    paths = {
        "com": p1 / "catia_full_extraction.json",
        "gap": p1 / "com_gap_report.json",
        "vision": p2 / "vision_report.json",
        "ocr": p2 / "ocr_report.json",
        "unified": un / "engineering_report.json",
        "validation": un / "validation_report.json",
        "human_review": un / "human_review_report.json",
        "final": un / "final_engineering_report.json",
    }
    # A "complete" export must not silently omit any pipeline stage.
    required = set(paths)
    reports = {
        name: read_json(path, required=(name in required))
        for name, path in paths.items()
    }
    com, final = reports["com"], reports["final"]
    com_name = (com.get("document") or {}).get("name")
    if com_name != final.get("document"):
        raise ValueError("CATIA document mismatch between COM and final report")

    meta = [{"source": key, "file": str(path), "present": path.is_file(),
             "sha256": sha256_file(path)} for key, path in paths.items()]
    tables = build_tables(com, final, reports, meta)

    bundle = {
        "export_version": "engineering-export-v1",
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "document": com_name,
        "engineering_approval": final.get("engineering_approval") is True,
        "sources": meta,
        "source_reports_full": reports,  # Never discard nested COM/OCR diagnostics.
    }
    full_json = destination / "engineering_export_complete.json"
    full_json.write_text(json.dumps(bundle, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    csv_paths = write_csv_tables(destination / "csv", tables)

    excel = destination / "engineering_data.xlsx"
    excel_ok = False
    try:
        write_excel(excel, tables)
        excel_ok = True
    except ImportError:
        print("Excel skipped: openpyxl not installed.")
        print("Complete JSON and CSV files were exported successfully.")

    print("\n========== COMPLETE ENGINEERING EXPORT ==========")
    print("Document:", com_name)
    print("COM extractors:", len(com.get("extractor_results") or {}))
    print("Approved GD&T:", sum(x.get("approved") is True
                              for x in tables["Approved GDT"]))
    print("Excel:", str(excel) if excel_ok else "not generated")
    print("CSV sheets:", len(csv_paths), "in", destination / "csv")
    print("Complete JSON:", full_json)
    return {"excel": str(excel) if excel_ok else None,
            "json": str(full_json), "csv": csv_paths}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Complete CATIA engineering export")
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    run(args.project_root)
