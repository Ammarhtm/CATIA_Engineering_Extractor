
import json
from pathlib import Path
from typing import Any


PIPELINE_VERSION = "2.3-visual-fallback-integration"


# Map fields reported by Pipeline 1 to canonical OCR fields.
FIELD_CANDIDATE_MAP = {
    "geometric_symbol": "geometric_symbol",
    "tolerance_value": "tolerance_value",
    "datum_reference": "datum_reference",
    "datum": "datum_reference",
    "diameter_modifier": "diameter_modifier",
    "material_condition": "material_condition",
    "displayed_tolerance_frame_content": (
        "displayed_tolerance_frame_content"
    ),
    "dimension_value": "dimension_value",
}


SOURCE_KEYS = {
    "geometric_symbol": (
        "geometric_symbol_candidate",
    ),
    "tolerance_value": (
        "tolerance_value_candidate",
        "numeric_candidate",
    ),
    "datum_reference": (
        "datum_candidate",
        "datum_reference_candidate",
    ),
    "diameter_modifier": (
        "diameter_modifier_candidate",
    ),
    "material_condition": (
        "material_condition_candidate",
    ),
    "dimension_value": (
        "dimension_value_candidate",
        "numeric_candidate",
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON without modifying the source file."""
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def discover_ocr_reports(
    directory: Path,
) -> dict[str, dict[str, Any]]:
    """Discover per-annotation reports and a consolidated summary."""
    reports: dict[str, dict[str, Any]] = {}

    if not directory.is_dir():
        return reports

    for path in sorted(directory.glob("*_ocr_report.json")):
        try:
            report = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue

        annotation = report.get("annotation")

        if annotation:
            reports[str(annotation)] = report

    # The summary is used only as a fallback when a per-annotation
    # report for the same annotation has not already been discovered.
    summary_path = directory / "pipeline_summary.json"

    if summary_path.is_file():
        try:
            summary = load_json(summary_path)
        except (OSError, json.JSONDecodeError):
            summary = {}

        for item in summary.get("results", []):
            annotation = item.get("annotation")

            if annotation:
                reports.setdefault(str(annotation), item)

    return reports


def _present(value: Any) -> bool:
    """Treat zero and False as valid values."""
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True


def _get_candidate(
    report: dict[str, Any],
    canonical_field: str,
) -> Any:
    """Read candidates from either supported V7.1 report structure."""
    interpretation = report.get("interpretation_candidate") or {}

    for key in SOURCE_KEYS.get(canonical_field, ()):
        if key in interpretation:
            candidate = interpretation[key]

            if _present(candidate):
                return candidate

    # Consolidated pipeline_summary.json stores candidates at the root.
    summary_keys = {
        "geometric_symbol": "geometric_symbol_candidate",
        "tolerance_value": "tolerance_value_candidate",
        "datum_reference": "datum_candidate",
        "diameter_modifier": "diameter_modifier_candidate",
        "material_condition": "material_condition_candidate",
        "dimension_value": "dimension_value_candidate",
    }

    summary_key = summary_keys.get(canonical_field)

    if summary_key and summary_key in report:
        candidate = report[summary_key]

        if _present(candidate):
            return candidate

    # An explicit frame-level candidate is accepted only when supplied
    # by a source report. Individual components do not imply a full frame.
    if canonical_field == "displayed_tolerance_frame_content":
        candidate = interpretation.get(canonical_field)

        if candidate is None:
            candidate = report.get(canonical_field)

        if _present(candidate):
            return candidate

    additional = interpretation.get("additional_candidates") or {}

    if canonical_field in additional:
        candidate = additional[canonical_field]

        if _present(candidate):
            return candidate

    return None


def extract_candidates(
    report: dict[str, Any],
) -> dict[str, Any]:
    """Normalize available OCR evidence without inventing frame content."""
    fields = (
        "geometric_symbol",
        "tolerance_value",
        "datum_reference",
        "diameter_modifier",
        "material_condition",
        "dimension_value",
        "displayed_tolerance_frame_content",
    )

    return {
        field: _get_candidate(report, field)
        for field in fields
    }


def normalize_missing_fields(
    gap: dict[str, Any],
) -> list[str]:
    """Support both current and legacy gap-report formats."""
    fields = gap.get("missing_fields")

    if fields is None:
        fields = gap.get("unresolved_items", [])

    normalized = []

    for item in fields:
        field = item.get("item") if isinstance(item, dict) else item

        if field:
            normalized.append(str(field))

    return list(dict.fromkeys(normalized))


def candidate_status(candidate: Any) -> str:
    """Report candidate availability without implying correctness."""
    if not _present(candidate):
        return "no_candidate_available"

    if isinstance(candidate, dict):
        if candidate.get("value") is None:
            # Explicit frame candidates may use another structure,
            # but a component candidate must contain a usable value.
            if not candidate.get("components"):
                return "candidate_unavailable"

    return "candidate_available_needs_validation"


def build_field_evidence(
    missing_fields: list[str],
    candidates: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Attach evidence only to fields marked missing by Pipeline 1."""
    evidence = {}

    for field in missing_fields:
        canonical_field = FIELD_CANDIDATE_MAP.get(field)
        candidate = (
            candidates.get(canonical_field)
            if canonical_field is not None
            else None
        )

        evidence[field] = {
            "status": candidate_status(candidate),
            "candidate": candidate,
        }

    return evidence


def build_visual_fallback_report(
    gap_report: dict[str, Any],
    ocr_reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Merge Pipeline 1 gaps with OCR evidence.

    Pipeline 1 remains the source of extracted metadata.
    OCR provides supplementary candidates only.
    No engineering approval is granted automatically.
    """
    gaps = gap_report.get("gaps")

    if gaps is None:
        gaps = gap_report.get("unresolved_annotations", [])

    results = []

    for gap in gaps:
        annotation = (
            gap.get("annotation_name")
            or gap.get("annotation_id")
            or "UNKNOWN"
        )

        missing_fields = normalize_missing_fields(gap)
        ocr_report = ocr_reports.get(str(annotation))

        candidates = (
            extract_candidates(ocr_report)
            if ocr_report is not None
            else {}
        )

        field_evidence = build_field_evidence(
            missing_fields,
            candidates,
        )

        available_count = sum(
            item["status"] == "candidate_available_needs_validation"
            for item in field_evidence.values()
        )

        unavailable_count = (
            len(field_evidence) - available_count
        )

        if not missing_fields:
            status = "no_missing_fields_reported"
        elif available_count:
            status = "needs_validation"
        else:
            status = "pending_visual_extraction"

        results.append({
            "annotation_name": annotation,
            "annotation_id": gap.get("annotation_id"),
            "annotation_type": gap.get("annotation_type"),
            "missing_fields": missing_fields,
            "ocr_report_available": ocr_report is not None,
            "ocr_candidates": candidates,
            "field_evidence": field_evidence,
            "counts": {
                "fields_reviewed": len(field_evidence),
                "candidate_available": available_count,
                "candidate_unavailable": unavailable_count,
            },
            "status": status,
            "engineering_approval": False,
        })

    return {
        "pipeline_version": PIPELINE_VERSION,
        "mode": "read_only",
        "source_pipeline": gap_report.get("pipeline_version"),
        "annotations_reviewed": len(results),
        "ocr_reports_discovered": len(ocr_reports),
        "results": results,
        "engineering_approval": False,
    }


def run_visual_fallback(
    gap_report_path: Path,
    ocr_directory: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Read source reports, generate the fallback report, and save it."""
    gap_report = load_json(gap_report_path)
    ocr_reports = discover_ocr_reports(ocr_directory)

    result = build_visual_fallback_report(
        gap_report,
        ocr_reports,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Verify the saved output is valid JSON.
    load_json(output_path)

    return result
