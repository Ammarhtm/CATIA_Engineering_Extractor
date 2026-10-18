
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


ROOT = Path.cwd()
OUTPUT_DIR = ROOT / "output" / "pipeline_v1"


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

    if value is None or isinstance(
        value, (str, int, float, bool)
    ):
        return value

    return repr(value)


def read_property(obj, name):
    try:
        value = getattr(obj, name)

        if callable(value):
            value = value()

        return {
            "status": "success",
            "value": json_safe(value),
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "value": None,
            "error": repr(exc),
        }


def inventory_annotations(part):
    annotation_sets = []

    for set_index in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(set_index)
        annotations = []

        for index in range(
            1, annotation_set.Annotations.Count + 1
        ):
            annotation = annotation_set.Annotations.Item(index)

            annotations.append({
                "index": index,
                "properties": {
                    name: read_property(annotation, name)
                    for name in (
                        "Name",
                        "Type",
                        "SuperType",
                        "TPSStatus",
                    )
                },
            })

        annotation_sets.append({
            "index": set_index,
            "name": read_property(annotation_set, "Name"),
            "annotations": annotations,
        })

    return {
        "annotation_set_count": len(annotation_sets),
        "annotation_count": sum(
            len(item["annotations"])
            for item in annotation_sets
        ),
        "annotation_sets": annotation_sets,
    }


def inventory_feature_tree(part):
    bodies = []

    for body_index in range(1, part.Bodies.Count + 1):
        body = part.Bodies.Item(body_index)
        shapes = []

        for shape_index in range(1, body.Shapes.Count + 1):
            shape = body.Shapes.Item(shape_index)

            shapes.append({
                "index": shape_index,
                "name": read_property(shape, "Name"),
                "type": read_property(shape, "Type"),
            })

        bodies.append({
            "index": body_index,
            "name": read_property(body, "Name"),
            "shapes_count": len(shapes),
            "shapes": shapes,
        })

    return {
        "body_count": len(bodies),
        "bodies": bodies,
    }


def run_extractor(function, *args):
    try:
        data = json_safe(function(*args))

        result = {
            "status": "success",
            "data": data,
            "error": None,
        }

        if isinstance(data, (list, dict)):
            result["count"] = len(data)

        return result

    except Exception as exc:
        return {
            "status": "failed",
            "count": None,
            "data": None,
            "error": repr(exc),
        }


def build_gap_report(extraction):
    gaps = []

    results = extraction["extractor_results"]
    nonsemantic = results.get("nonsemantic_gdt", {})

    if nonsemantic.get("status") == "success":
        for annotation in nonsemantic.get("data") or []:
            name = annotation.get("annotation_name")

            gaps.append({
                "annotation_name": name,
                "annotation_type": annotation.get(
                    "annotation_type"
                ),
                "known_metadata": {
                    "super_type": annotation.get("super_type"),
                    "tps_status": annotation.get("tps_status"),
                    "surfaces": annotation.get("surfaces"),
                },
                "unresolved_items": [
                    "geometric_symbol",
                    "displayed_tolerance_frame_content",
                ],
                "next_action": (
                    "Visual extraction required after COM "
                    "pipeline review"
                ),
                "engineering_approval": False,
            })

    failed_extractors = [
        {
            "extractor": name,
            "error": result.get("error"),
        }
        for name, result in results.items()
        if result.get("status") == "failed"
    ]

    return {
        "pipeline_version": "1.0-com-gap-report",
        "document": extraction["document"]["name"],
        "mode": "read_only",
        "unresolved_annotations": gaps,
        "failed_extractors": failed_extractors,
        "engineering_approval": False,
    }


def run_pipeline():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    session = connect_to_catia()
    document = session.document
    part = document.Part

    tree_inventory = inventory_annotations(part)
    feature_tree = inventory_feature_tree(part)

    extractor_results = {
        "part_parameters_and_features": run_extractor(
            read_catia_part, session
        ),
        "semantic_gdt": run_extractor(extract_gdt, part),
        "datums": run_extractor(extract_datums, part),
        "dimensions": run_extractor(extract_dimensions, part),
        "nonsemantic_gdt": run_extractor(
            extract_nonsemantic_gdt, part
        ),
        "reference_frames": run_extractor(
            extract_reference_frames, part
        ),
    }

    extraction = {
        "pipeline_version": "2.0-com-extraction",
        "document": {
            "name": str(document.Name),
            "part_name": str(part.Name),
            "mode": "read_only",
        },
        "tree_inventory": tree_inventory,
        "feature_tree": feature_tree,
        "extractor_results": extractor_results,
        "engineering_approval": False,
    }

    extraction_path = OUTPUT_DIR / "catia_full_extraction.json"
    extraction_path.write_text(
        json.dumps(
            extraction,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    gap_report = build_gap_report(extraction)

    gap_path = OUTPUT_DIR / "com_gap_report.json"
    gap_path.write_text(
        json.dumps(
            gap_report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Verify both saved files can be reopened.
    json.loads(extraction_path.read_text(encoding="utf-8"))
    json.loads(gap_path.read_text(encoding="utf-8"))

    print("\n====== CATIA COM PIPELINE ======")
    print("Document:", document.Name)
    print("Annotation sets:", tree_inventory["annotation_set_count"])
    print("Annotations:", tree_inventory["annotation_count"])
    print("Bodies:", feature_tree["body_count"])

    for name, result in extractor_results.items():
        data = result.get("data")
        count = result.get("count")

        if count is None and isinstance(data, dict):
            count = len(data.get("parameters", []))

        print(
            name,
            "| status:", result["status"],
            "| count:", count,
        )

        if result["status"] == "failed":
            print("  Error:", result["error"])

    print("\nExtraction JSON:", extraction_path.resolve())
    print("COM gap report:", gap_path.resolve())

    return extraction


if __name__ == "__main__":
    run_pipeline()
