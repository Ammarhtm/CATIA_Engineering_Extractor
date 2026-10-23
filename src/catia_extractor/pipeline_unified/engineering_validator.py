"""Conservative engineering evidence validator for the unified CATIA report.

Run from project root (without opening CATIA):
    python -m catia_extractor.pipeline_unified.engineering_validator

Produces a separate validation_report.json; never grants engineering approval.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NUMERIC = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)$")


def _read(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(" ", "")
    if not NUMERIC.fullmatch(text):
        return None
    try:
        number = Decimal(text.replace(",", "."))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def _issue(issues, severity, code, detail):
    issues.append({"severity": severity, "code": code, "detail": detail})


def _index_by_id(report: dict, source: str) -> dict:
    indexed = {}
    for row in report.get("results", []):
        key = row.get("annotation_id")
        if not key or key in indexed:
            raise ValueError(f"{source}: missing or duplicate annotation_id: {key!r}")
        indexed[key] = row
    return indexed


def validate_annotation(item: dict, ocr_source: dict | None) -> dict:
    issues = []
    annotation_id = item.get("annotation_id")
    frame = item.get("full_frame") or {}
    ocr = item.get("ocr") or {}

    if item.get("selection_confirmed") is not True:
        _issue(issues, "blocker", "SELECTION_UNCONFIRMED", "CATIA selection not confirmed")

    box = frame.get("box")
    valid_box = (
        isinstance(box, (list, tuple)) and len(box) == 4
        and all(type(n) is int for n in box)
        and box[0] >= 0 and box[1] >= 0
        and box[2] > 0 and box[3] > 0
    )
    if frame.get("status") != "full_frame_candidate_needs_review" or not valid_box:
        _issue(issues, "blocker", "FRAME_NOT_ESTABLISHED", "No valid full-frame candidate")

    image_path = frame.get("image")
    if not image_path or not Path(image_path).is_file():
        _issue(issues, "blocker", "IMAGE_MISSING", "Full-frame evidence image is missing")

    evidence = frame.get("border_evidence") or {}
    for edge in ("top_border", "bottom_border", "left_wall", "right_wall"):
        score = evidence.get(edge)
        if not isinstance(score, (int, float)) or not (0 <= score <= 1):
            _issue(issues, "warning", "BORDER_EVIDENCE_MISSING", f"{edge} not measurable")
        elif score < (0.60 if edge in ("top_border", "bottom_border") else 0.40):
            _issue(issues, "warning", "WEAK_BORDER_EVIDENCE", f"{edge} coverage = {score}")

    if ocr.get("status") != "needs_visual_review" or ocr.get("error"):
        _issue(issues, "blocker", "OCR_NOT_ESTABLISHED", "OCR not completed successfully")

    symbol = ocr.get("geometric_symbol") or {}
    if not isinstance(symbol, dict) or not symbol.get("name") or not symbol.get("glyph"):
        _issue(issues, "blocker", "SYMBOL_MISSING", "Geometric symbol has not been identified")
    else:
        match_score = symbol.get("match_score")
        if not isinstance(match_score, (int, float)) or not (0 <= match_score <= 1):
            _issue(issues, "warning", "SYMBOL_SCORE_MISSING", "No usable template match score")
        elif match_score < 0.85:
            _issue(issues, "warning", "LOW_SYMBOL_MATCH", f"Template match score = {match_score}")

    tolerance = ocr.get("tolerance") or {}
    raw_value = _decimal(tolerance.get("raw")) if isinstance(tolerance, dict) else None
    parsed_value = _decimal(tolerance.get("value")) if isinstance(tolerance, dict) else None
    if raw_value is None or parsed_value is None:
        _issue(issues, "blocker", "TOLERANCE_UNREADABLE", "Tolerance is missing or not a valid number")
    elif raw_value != parsed_value or raw_value < 0:
        _issue(issues, "blocker", "TOLERANCE_INCONSISTENT", "Tolerance text/value mismatch or negative")
    elif raw_value == 0:
        _issue(issues, "warning", "ZERO_TOLERANCE_REVIEW", "OCR returned zero: verify exact value in CATIA")

    datums = ocr.get("datum_references")
    if not isinstance(datums, list):
        _issue(issues, "blocker", "DATUM_FORMAT", "Datum references should be a list")
    elif any(not isinstance(d, str) or not d.strip() for d in datums):
        _issue(issues, "blocker", "DATUM_UNREADABLE", "At least one datum reference is invalid")
    elif len(datums) != len(set(datums)):
        _issue(issues, "warning", "REPEATED_DATUM", "A datum reference appears more than once")
    # No mandatory-datum rule: some GD&T characteristics legitimately have none.

    if ocr.get("warnings"):
        _issue(issues, "warning", "OCR_WARNINGS", "OCR engine reported warnings")

    if ocr_source is None:
        _issue(issues, "blocker", "OCR_SOURCE_MISSING", "No matching original OCR record")
    else:
        if ocr_source.get("status") != ocr.get("status"):
            _issue(issues, "blocker", "OCR_SOURCE_MISMATCH", "OCR status differs from source")
        for field in ("geometric_symbol", "tolerance", "diameter_modifier",
                      "material_condition_modifier", "datum_references"):
            if ocr_source.get(field) != ocr.get(field):
                _issue(issues, "blocker", "OCR_SOURCE_MISMATCH", f"{field} differs from source OCR")
        if image_path and ocr_source.get("full_frame_file") != image_path:
            _issue(issues, "blocker", "IMAGE_SOURCE_MISMATCH", "Full-frame image path differs from source")

        # OCR alternatives are diagnostic signals, not ground-truth confirmation.
        raw_ocr = ocr_source.get("raw_ocr") or {}
        value_observations = raw_ocr.get("value_filtered", []) + raw_ocr.get("numeric_roi", [])
        if raw_value is not None:
            alternatives = [
                str(obs.get("text", "")).strip()
                for obs in value_observations if isinstance(obs, dict)
            ]
            different = [
                text for text in alternatives
                if text and _decimal(text) != raw_value
            ]
            if different:
                _issue(issues, "warning", "OCR_NUMERIC_AMBIGUITY",
                       f"Some OCR readings disagree or are incomplete: {different[:4]}")

    blockers = sum(x["severity"] == "blocker" for x in issues)
    warnings = sum(x["severity"] == "warning" for x in issues)
    status = (
        "blocked" if blockers
        else "needs_attention" if warnings
        else "ready_for_human_review"
    )
    return {
        "annotation_id": annotation_id,
        "annotation_name": item.get("annotation_name"),
        "status": status,
        "automatic_checks_passed": blockers == 0,
        "engineering_approval": False,
        "blocker_count": blockers,
        "warning_count": warnings,
        "issues": issues,
        "review_image": image_path,
        "extracted_values": {
            "geometric_symbol": symbol.get("glyph") if isinstance(symbol, dict) else None,
            "tolerance": tolerance.get("raw") if isinstance(tolerance, dict) else None,
            "diameter_modifier": ocr.get("diameter_modifier"),
            "material_condition_modifier": ocr.get("material_condition_modifier"),
            "datum_references": datums,
        },
    }


def run(project_root=None) -> dict:
    root = Path(project_root) if project_root else ROOT
    report_dir = root / "output" / "pipeline_unified"
    unified_path = report_dir / "engineering_report.json"
    unified = _read(unified_path)

    ocr_path = Path(unified["sources"]["ocr_report"])
    if not ocr_path.is_file():
        raise FileNotFoundError(f"Original OCR report missing: {ocr_path}")
    ocr_original = _read(ocr_path)
    ocr_by_id = _index_by_id(ocr_original, "Original OCR")
    combined_by_id = _index_by_id(unified, "Unified report")
    results = [
        validate_annotation(item, ocr_by_id.get(key))
        for key, item in combined_by_id.items()
    ]
    unmatched_ocr_ids = sorted(set(ocr_by_id) - set(combined_by_id))
    status_counts = {status: sum(x["status"] == status for x in results)
                     for status in ("ready_for_human_review", "needs_attention", "blocked")}
    result = {
        "validator_version": "engineering-validator-v1",
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "document": unified.get("document"),
        "source_report": str(unified_path),
        "engineering_approval": False,
        "summary": {
            "annotations_checked": len(results),
            **status_counts,
            "awaiting_human_approval": len(results),
            "unmatched_ocr_records": len(unmatched_ocr_ids),
        },
        "unmatched_ocr_ids": unmatched_ocr_ids,
        "results": results,
    }
    destination = report_dir / "validation_report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n========== ENGINEERING VALIDATION ==========")
    for row in results:
        print(f"{row['annotation_name']}: {row['status']} "
              f"(blockers={row['blocker_count']}, warnings={row['warning_count']})")
        for issue in row["issues"]:
            print(f"  - [{issue['severity']}] {issue['code']}: {issue['detail']}")
    print("Engineering approval: False (requires human sign-off)")
    print("Validation report:", destination)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=None)
    run(parser.parse_args().project_root)
