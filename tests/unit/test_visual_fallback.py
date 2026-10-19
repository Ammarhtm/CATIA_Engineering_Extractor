
from catia_extractor.pipelines.visual_fallback import (
    build_visual_fallback_report,
)


def test_matches_existing_ocr_candidates_dynamically():
    gaps = {
        "pipeline_version": "2.0-gap-analysis",
        "gaps": [
            {
                "annotation_name": "Tolerance A",
                "missing_fields": [
                    "geometric_symbol",
                    "displayed_tolerance_frame_content",
                ],
            },
            {
                "annotation_name": "Dimension B",
                "missing_fields": ["dimension_value"],
            },
        ],
    }

    ocr_reports = {
        "Tolerance A": {
            "interpretation_candidate": {
                "geometric_symbol_candidate": {
                    "value": "perpendicularity",
                    "score": 0.83,
                }
            }
        }
    }

    result = build_visual_fallback_report(gaps, ocr_reports)

    assert result["annotations_reviewed"] == 2

    first = result["results"][0]
    assert first["field_evidence"]["geometric_symbol"]["status"] == (
        "candidate_available_needs_validation"
    )
    assert first["field_evidence"][
        "displayed_tolerance_frame_content"
    ]["status"] == "no_candidate_available"

    second = result["results"][1]
    assert second["status"] == "pending_visual_extraction"

    assert result["engineering_approval"] is False


def test_zero_is_preserved_as_a_candidate():
    gaps = {
        "gaps": [
            {
                "annotation_name": "Tolerance C",
                "missing_fields": ["tolerance_value"],
            }
        ]
    }

    reports = {
        "Tolerance C": {
            "interpretation_candidate": {
                "tolerance_value_candidate": {
                    "value": 0.0,
                    "raw": "0",
                }
            }
        }
    }

    result = build_visual_fallback_report(gaps, reports)

    evidence = result["results"][0]["field_evidence"]["tolerance_value"]

    assert evidence["candidate"]["value"] == 0.0
    assert evidence["status"] == "candidate_available_needs_validation"
