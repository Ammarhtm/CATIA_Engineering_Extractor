from catia_extractor.pipelines.gap_analyzer import (
    analyze_missing_fields,
)


def test_only_missing_fields_are_scheduled():
    required = {
        "annotation_A": [
            "geometric_symbol",
            "tolerance_value",
        ],
        "annotation_B": [
            "dimension_value",
        ],
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
    assert tasks[0]["engineering_approval"] is False
