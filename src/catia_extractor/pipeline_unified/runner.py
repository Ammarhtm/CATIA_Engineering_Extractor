"""Single entrypoint: CATIA COM -> vision full frames -> GD&T OCR -> report.

Keeps the existing stage implementations and their diagnostic artifacts.
Run on Windows with CATIA V5 open:
    python -m catia_extractor.pipeline_unified.runner

All recognized engineering fields are provisional and require human review.
"""




from __future__ import annotations

from catia_extractor.pipeline_unified.engineering_validator import (
    run as run_validation,
)

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from catia_extractor.pipeline_v1.runner import run_pipeline as run_com
from catia_extractor.pipeline_v2.runner import run_pipeline as run_vision
from catia_extractor.ocr.run_from_pipeline2 import run as run_ocr

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "output"
DESTINATION = OUTPUT / "pipeline_unified" / "engineering_report.json"
VISION_PATH = OUTPUT / "pipeline_v2" / "vision_report.json"
OCR_PATH = OUTPUT / "pipeline_v2" / "ocr_report.json"
GAP_PATH = OUTPUT / "pipeline_v1" / "com_gap_report.json"


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _index_results(rows: list[dict], source: str) -> dict[str, dict]:
    indexed = {}
    for row in rows:
        key = row.get("annotation_id")
        if not key:
            raise ValueError(f"{source}: record without annotation_id")
        if key in indexed:
            raise ValueError(f"{source}: duplicate annotation_id {key!r}")
        indexed[key] = row
    return indexed


def _matches_vision(ocr_report: dict, vision_report: dict) -> bool:
    """Prevent reuse of an OCR report for a different visual run."""
    try:
        same_source = (
            Path(ocr_report["source_report"]).resolve()
            == VISION_PATH.resolve()
        )
        vision_ids = set(_index_results(vision_report.get("results", []), "vision"))
        ocr_ids = set(_index_results(ocr_report.get("results", []), "OCR"))
        return same_source and vision_ids == ocr_ids
    except (KeyError, TypeError, ValueError):
        return False


def _combine(vision: dict, ocr: dict) -> list[dict]:
    ocr_by_id = _index_results(ocr.get("results", []), "OCR")
    vision_by_id = _index_results(vision.get("results", []), "vision")
    if set(ocr_by_id) != set(vision_by_id):
        raise ValueError("OCR and vision annotation_id sets differ; refusing to merge")

    combined = []
    for annotation_id, visual in vision_by_id.items():
        reading = ocr_by_id[annotation_id]
        frame = visual.get("full_frame") or {}
        has_frame = bool(frame.get("box")) and (
            frame.get("status") == "full_frame_candidate_needs_review"
        )
        has_ocr = reading.get("status") == "needs_visual_review"

        if not has_frame:
            status = "full_frame_not_established"
        elif not has_ocr:
            status = "ocr_not_established"
        else:
            status = "ocr_candidate_needs_review"

        combined.append({
            "annotation_id": annotation_id,
            "annotation_name": visual.get("annotation_name"),
            "annotation_type": visual.get("annotation_type"),
            "known_com_metadata": visual.get("known_metadata", {}),
            "fields_missing_from_com": visual.get("missing_fields", []),
            "status": status,
            "selection_confirmed": visual.get("selection_confirmed", False),
            "full_frame": {
                "status": frame.get("status"),
                "box": frame.get("box"),
                "image": reading.get("full_frame_file") if has_frame else None,
                "border_evidence": frame.get("border_evidence"),
            },
            "ocr": {
                "status": reading.get("status"),
                "geometric_symbol": reading.get("geometric_symbol") if has_ocr else None,
                "tolerance": reading.get("tolerance") if has_ocr else None,
                "diameter_modifier": reading.get("diameter_modifier") if has_ocr else None,
                "material_condition_modifier": (
                    reading.get("material_condition_modifier") if has_ocr else None
                ),
                "datum_references": reading.get("datum_references", []) if has_ocr else [],
                "warnings": reading.get("warnings", []),
                "error": reading.get("error"),
            },
            "engineering_approval": False,
        })
    return combined


def run_pipeline() -> dict:
    print("\n========= UNIFIED CATIA PIPELINE =========")
    print("[1/4] CATIA COM extraction and gap analysis")
    com_report = run_com()
    gap_report = _load_json(GAP_PATH)

    print("\n[2/4] Selection, full-frame location and capture")
    vision_started_ns = time.time_ns()
    vision_report = run_vision()

    com_document = (com_report.get("document") or {}).get("name")
    visual_document = vision_report.get("document")
    if com_document and visual_document and com_document != visual_document:
        raise RuntimeError(
            f"CATIA document changed between stages: {com_document!r} != {visual_document!r}"
        )
    if com_document and gap_report.get("document") != com_document:
        raise RuntimeError("COM extraction and gap report refer to different documents")

    print("\n[3/4] GD&T OCR")
    # A prior optional Pipeline 2 modification may already have run OCR.
    # Reuse it ONLY when written during this visual run and IDs match.
    existing = None
    if OCR_PATH.is_file() and OCR_PATH.stat().st_mtime_ns >= vision_started_ns:
        candidate = _load_json(OCR_PATH)
        if _matches_vision(candidate, vision_report):
            existing = candidate
    if existing is not None:
        print("OCR already produced by Pipeline 2; avoiding duplicate execution")
        ocr_report = existing
    else:
        ocr_report = run_ocr(project_root=ROOT)
    if not _matches_vision(ocr_report, vision_report):
        raise RuntimeError("OCR report does not match current vision report")

    print("\n[4/4] Combine matching annotation IDs")
    records = _combine(vision_report, ocr_report)
    frames = sum(item["full_frame"]["box"] is not None for item in records)
    recognized = sum(item["status"] == "ocr_candidate_needs_review" for item in records)
    failures = len(records) - recognized

    pending_reviews = sum(
    not item.get("engineering_approval", False)
    for item in records
)

    final_report = {
        "pipeline_version": "unified-pilot-v1",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "document": com_document or visual_document,
        "processing_status": (
            "no_visual_tasks" if not records
            else "needs_review" if not failures
            else "incomplete_needs_review"
        ),
        "engineering_approval": False,
        "sources": {
            "com_extraction": str(OUTPUT / "pipeline_v1" / "catia_full_extraction.json"),
            "com_gap_report": str(GAP_PATH),
            "vision_report": str(VISION_PATH),
            "ocr_report": str(OCR_PATH),
        },
        "summary": {
            "annotations": len(records),
            "full_frame_candidates": frames,
            "ocr_candidates": recognized,
            "annotations_needing_followup": pending_reviews,
            "annotations_with_extraction_issue": failures,
            "failed_com_extractors": len(gap_report.get("failed_extractors", [])),
            "vision_task_failures": vision_report.get("tasks_failed", 0),
        },
        "results": records,
    }
    _save_json(DESTINATION, final_report)

    # ========================================
    # STEP 5: ENGINEERING VALIDATION
    # ========================================

    print("\n[5/5] Engineering Validation")

    validation_report = run_validation(
        project_root=ROOT
    )

    validation_summary = validation_report["summary"]

    final_report["sources"]["validation_report"] = str(
        OUTPUT / "pipeline_unified" / "validation_report.json"
    )

    final_report["summary"]["ready_for_human_review"] = (
        validation_summary["ready_for_human_review"]
    )

    final_report["summary"]["needs_attention"] = (
        validation_summary["needs_attention"]
    )

    final_report["summary"]["blocked"] = (
        validation_summary["blocked"]
    )

    # Save updated unified report
    _save_json(DESTINATION, final_report)

    print("\n========== VALIDATION SUMMARY ==========")
    print("Ready for review:",
          validation_summary["ready_for_human_review"])
    print("Needs attention:",
          validation_summary["needs_attention"])
    print("Blocked:",
          validation_summary["blocked"])
    print("Engineering approval: False")

    print("\n========= FINAL RESULTS =========")
    print("Annotations:", len(records))
    print("Full frames:", frames)
    print("OCR candidates:", recognized)
    print("Engineering approval: False (human review required)")
    print("Unified report:", DESTINATION)
    return final_report


if __name__ == "__main__":
    run_pipeline()
