
from catia_extractor.pipelines.gap_analyzer import (
    analyze_missing_fields,
)


def test_only_missing_fields_are_scheduled():
    required = {
        "annotation_A": [
            "geometric_symbol",
            "tolerance_value",
        ],
        "annotation_B": ["dimension_value"],
    }

    extracted = {
        "annotation_A": {
            "geometric_symbol": None,
            "tolerance_value": 0.1,
        },
        "annotation_B": {
            "dimension_value": 25.0,
        },
    }

    tasks = analyze_missing_fields(required, extracted)

    assert len(tasks) == 1
    assert tasks[0]["annotation_id"] == "annotation_A"
    assert tasks[0]["missing_fields"] == ["geometric_symbol"]


def test_zero_and_false_are_valid_values():
    required = {
        "annotation_A": ["tolerance_value", "diameter_modifier"],
    }

    extracted = {
        "annotation_A": {
            "tolerance_value": 0.0,
            "diameter_modifier": False,
        }
    }

    tasks = analyze_missing_fields(required, extracted)

    assert tasks == []


def test_empty_string_is_missing():
    required = {"annotation_A": ["geometric_symbol"]}
    extracted = {"annotation_A": {"geometric_symbol": "  "}}

    tasks = analyze_missing_fields(required, extracted)

    assert len(tasks) == 1
    assert tasks[0]["missing_fields"] == ["geometric_symbol"]


def test_unknown_annotation_is_handled():
    required = {"annotation_A": ["geometric_symbol"]}

    tasks = analyze_missing_fields(required, {})

    assert len(tasks) == 1
    assert tasks[0]["annotation_id"] == "annotation_A"
    assert tasks[0]["status"] == "pending_visual_extraction"
    assert tasks[0]["engineering_approval"] is False


def test_complete_annotation_is_not_scheduled():
    required = {"annotation_A": ["tolerance_value"]}
    extracted = {"annotation_A": {"tolerance_value": 0.055}}

    assert analyze_missing_fields(required, extracted) == []
