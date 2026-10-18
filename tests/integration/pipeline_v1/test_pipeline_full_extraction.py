import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.catia.com_reader import read_catia_part
from catia_extractor.catia.gdt_extractor import extract_gdt
from catia_extractor.catia.datum_extractor import extract_datums
from catia_extractor.catia.dimension_extractor import extract_dimensions
from catia_extractor.catia.nonsemantic_gdt_extractor import (
    extract_nonsemantic_gdt,
)
from catia_extractor.catia.reference_frame_extractor import (
    extract_reference_frames,
)


OUTPUT = Path("output/pipeline_v1/catia_full_extraction.json")


def json_safe(value):
    if is_dataclass(value):
        return json_safe(asdict(value))

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return repr(value)


def run_extractor(name, function, part):
    try:
        result = function(part)

        return {
            "status": "success",
            "count": len(result),
            "data": json_safe(result),
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "count": None,
            "data": [],
            "error": repr(exc),
        }


def test_pipeline_full_extraction():
    session = connect_to_catia()
    document = session.document
    part = document.Part

    # 1. Complete annotation tree inventory
    annotation_sets = []

    for set_index in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(set_index)
        annotations = []

        for ann_index in range(
            1, annotation_set.Annotations.Count + 1
        ):
            ann = annotation_set.Annotations.Item(ann_index)

            properties = {}

            for prop in ("Name", "Type", "SuperType", "TPSStatus"):
                try:
                    value = getattr(ann, prop)
                    if callable(value):
                        value = value()

                    properties[prop] = {
                        "status": "read_successfully",
                        "value": json_safe(value),
                        "error": None,
                    }
                except Exception as exc:
                    properties[prop] = {
                        "status": "read_failed",
                        "value": None,
                        "error": repr(exc),
                    }

            annotations.append({
                "index": ann_index,
                "properties": properties,
            })

        try:
            set_name = str(annotation_set.Name)
            set_name_error = None
        except Exception as exc:
            set_name = None
            set_name_error = repr(exc)

        annotation_sets.append({
            "index": set_index,
            "name": set_name,
            "name_error": set_name_error,
            "annotations": annotations,
        })

    # 2. Existing extractors: run independently so one failure
    # does not prevent the remaining extractors from running.
    extractor_functions = {
        "part_parameters_and_features": (
            lambda: read_catia_part(session)
        ),
        "semantic_gdt": lambda: extract_gdt(part),
        "datums": lambda: extract_datums(part),
        "dimensions": lambda: extract_dimensions(part),
        "nonsemantic_gdt": lambda: extract_nonsemantic_gdt(part),
        "reference_frames": lambda: extract_reference_frames(part),
    }

    extraction_results = {}

    for name, function in extractor_functions.items():
        try:
            result = function()

            if name == "part_parameters_and_features":
                data = json_safe(result)
                extraction_results[name] = {
                    "status": "success",
                    "data": data,
                    "error": None,
                }
            else:
                extraction_results[name] = {
                    "status": "success",
                    "count": len(result),
                    "data": json_safe(result),
                    "error": None,
                }

        except Exception as exc:
            extraction_results[name] = {
                "status": "failed",
                "count": None,
                "data": None,
                "error": repr(exc),
            }

    report = {
        "pipeline_version": "1.1-full-extraction",
        "document": {
            "name": str(document.Name),
            "part_name": str(part.Name),
            "mode": "read_only",
        },
        "tree_inventory": {
            "annotation_set_count": len(annotation_sets),
            "annotation_count": sum(
                len(item["annotations"])
                for item in annotation_sets
            ),
            "annotation_sets": annotation_sets,
        },
        "extractor_results": extraction_results,
        "engineering_approval": False,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Verify the saved JSON can be reopened and parsed.
    saved = json.loads(OUTPUT.read_text(encoding="utf-8"))

    assert saved["document"]["name"] == document.Name
    assert saved["tree_inventory"]["annotation_count"] == 11

    print("\n====== PIPELINE V1 FULL EXTRACTION ======")
    print("Document:", saved["document"]["name"])
    print("AnnotationSets:",
          saved["tree_inventory"]["annotation_set_count"])
    print("Annotations:",
          saved["tree_inventory"]["annotation_count"])

    print("\n====== EXTRACTOR RESULTS ======")

    for name, result in saved["extractor_results"].items():
        print(
            name,
            "| status:", result["status"],
            "| count:", result.get("count", "n/a"),
        )

        if result["status"] == "failed":
            print("  Error:", result["error"])

    print("\nJSON valid:", True)
    print("Saved:", OUTPUT.resolve())
