
import json
from pathlib import Path

from catia_extractor.pipelines.evidence_aggregator import (
    aggregate_pipeline_summary,
)


ROOT = Path(__file__).resolve().parents[2]

SUMMARY_PATH = (
    ROOT
    / "output"
    / "debug"
    / "nonsemantic_v71"
    / "pipeline_summary.json"
)


def test_aggregator_preserves_existing_v71_results():
    summary = {
        "version": "7.1",
        "results": [
            {
                "annotation": "Geometrical Tolerance.1",
                "frame": [294, 724, 120, 31],
                "geometric_symbol_candidate": {
                    "value": "perpendicularity",
                    "score": 0.8372,
                },
                "tolerance_value_candidate": {
                    "value": 0.0,
                    "raw": "0",
                    "confidence": 0.9982,
                    "variant": "gray",
                },
                "datum_candidate": {
                    "value": "A",
                    "confidence": 0.9999,
                    "variant": "gray",
                },
                "diameter_modifier_candidate": True,
                "material_condition_candidate": "MMC",
                "numeric_evidence": {
                    "matching_variant_count": 1,
                    "matching_variants": ["gray"],
                    "status": "single_variant_support",
                },
                "evidence_scores": {
                    "diameter": 0.8718,
                    "mmc": 0.6119,
                },
            }
        ],
    }

    result = aggregate_pipeline_summary(summary)

    assert result["annotations_reviewed"] == 1
    assert result["engineering_approval"] is False

    item = result["results"][0]

    assert item["annotation"] == "Geometrical Tolerance.1"
    assert (
        item["fields"]["geometric_symbol"]["candidate"]["value"]
        == "perpendicularity"
    )
    assert (
        item["fields"]["tolerance_value"]["candidate"]["value"]
        == 0.0
    )
    assert (
        item["fields"]["datum_reference"]["candidate"]["value"]
        == "A"
    )
    assert item["numeric_agreement"]["matching_variant_count"] == 1
    assert item["status"] == "needs_validation"


def test_aggregator_reads_real_v71_summary():
    if not SUMMARY_PATH.is_file():
        return

    summary = json.loads(
        SUMMARY_PATH.read_text(encoding="utf-8")
    )

    result = aggregate_pipeline_summary(summary)

    assert result["annotations_reviewed"] == len(
        summary.get("results", [])
    )
    assert result["engineering_approval"] is False


def test_zero_is_not_treated_as_missing():
    report = {
        "version": "7.1",
        "annotation": "Tolerance Zero",
        "interpretation_candidate": {
            "tolerance_value_candidate": {
                "value": 0.0,
                "raw": "0",
                "confidence": 0.998,
            },
            "numeric_evidence": {
                "matching_variant_count": 1,
                "matching_variants": ["gray"],
            },
        },
    }

    from catia_extractor.pipelines.evidence_aggregator import (
        aggregate_annotation,
    )

    result = aggregate_annotation(report)

    numeric = result["fields"]["tolerance_value"]

    assert numeric["candidate"]["value"] == 0.0
    assert numeric["evidence_source"] == "ocr"
