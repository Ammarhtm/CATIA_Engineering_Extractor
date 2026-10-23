
"""Evidence Aggregator V7.2.

Consumes existing V7.1 OCR/template reports.
Does not rerun OCR, OpenCV, or template matching.
All candidates remain provisional pending visual validation.
"""

from typing import Any


VERSION = "7.2-evidence-aggregator"


def _candidate_value(candidate: Any) -> Any:
    """Read a candidate without treating 0 or False as missing."""
    if isinstance(candidate, dict):
        return candidate.get("value")
    return candidate


def _is_available(candidate: Any) -> bool:
    if candidate is None:
        return False

    value = _candidate_value(candidate)

    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True


def _read_candidate(
    report: dict[str, Any],
    interpretation: dict[str, Any],
    key: str,
) -> Any:
    """Support both nested V7.1 reports and flat pipeline summaries."""
    if key in interpretation:
        return interpretation[key]

    return report.get(key)


def aggregate_annotation(report: dict[str, Any]) -> dict[str, Any]:
    """Organize existing candidates and their supporting evidence."""
    interpretation = report.get("interpretation_candidate") or {}

    numeric = _read_candidate(
        report, interpretation, "tolerance_value_candidate"
    )
    datum = _read_candidate(
        report, interpretation, "datum_candidate"
    )
    symbol = _read_candidate(
        report, interpretation, "geometric_symbol_candidate"
    )
    diameter = _read_candidate(
        report, interpretation, "diameter_modifier_candidate"
    )
    material_condition = _read_candidate(
        report, interpretation, "material_condition_candidate"
    )

    numeric_evidence = (
        interpretation.get("numeric_evidence")
        or report.get("numeric_evidence")
        or {}
    )
    evidence_scores = (
        interpretation.get("evidence_scores")
        or report.get("evidence_scores")
        or {}
    )

    fields = {
        "geometric_symbol": {
            "candidate": symbol,
            "evidence_source": "template_matching",
            "score": (
                symbol.get("score")
                if isinstance(symbol, dict)
                else None
            ),
        },
        "tolerance_value": {
            "candidate": numeric,
            "evidence_source": "ocr",
            "confidence": (
                numeric.get("confidence")
                if isinstance(numeric, dict)
                else None
            ),
            "variant": (
                numeric.get("variant")
                if isinstance(numeric, dict)
                else None
            ),
            "variant_evidence": numeric_evidence,
        },
        "datum_reference": {
            "candidate": datum,
            "evidence_source": "ocr",
            "confidence": (
                datum.get("confidence")
                if isinstance(datum, dict)
                else None
            ),
            "variant": (
                datum.get("variant")
                if isinstance(datum, dict)
                else None
            ),
        },
        "diameter_modifier": {
            "candidate": diameter,
            "evidence_source": "template_matching",
            "score": evidence_scores.get("diameter"),
        },
        "material_condition": {
            "candidate": material_condition,
            "evidence_source": "template_matching",
            "score": evidence_scores.get("mmc"),
        },
    }

    review_reasons = []

    for field_name, evidence in fields.items():
        candidate = evidence["candidate"]

        if not _is_available(candidate):
            review_reasons.append({
                "field": field_name,
                "reason": "no_candidate_available",
            })
        else:
            review_reasons.append({
                "field": field_name,
                "reason": "candidate_requires_visual_validation",
            })

    variant_count = numeric_evidence.get(
        "matching_variant_count", 0
    )

    if _is_available(numeric) and variant_count < 2:
        review_reasons.append({
            "field": "tolerance_value",
            "reason": (
                "numeric_candidate_supported_by_fewer_than_two_variants"
            ),
        })

    return {
        "version": VERSION,
        "annotation": report.get("annotation"),
        "frame": report.get("frame"),
        "fields": fields,
        "numeric_agreement": {
            "matching_variant_count": variant_count,
            "matching_variants": numeric_evidence.get(
                "matching_variants", []
            ),
            "status": numeric_evidence.get(
                "status", "not_reported"
            ),
        },
        "review_reasons": review_reasons,
        "status": "needs_validation",
        "engineering_approval": False,
        "source_report_version": report.get("version"),
    }


def aggregate_pipeline_summary(
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate candidates from an existing V7.1 pipeline summary."""
    results = [
        aggregate_annotation(item)
        for item in summary.get("results", [])
    ]

    return {
        "version": VERSION,
        "source_version": summary.get("version"),
        "annotations_reviewed": len(results),
        "results": results,
        "status": "needs_validation",
        "engineering_approval": False,
        "note": (
            "Existing V7.1 candidates were reorganized. "
            "No OCR or template matching was rerun, and no "
            "engineering approval was inferred."
        ),
    }
