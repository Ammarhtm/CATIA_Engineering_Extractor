
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

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
from catia_extractor.pipelines.gap_analyzer import (
    analyze_missing_fields,
)
from catia_extractor.pipelines.visual_fallback import (
    run_visual_fallback,
)


ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = ROOT / "output" / "pipeline_v1"
OCR_REPORT_DIR = ROOT / "output" / "debug" / "nonsemantic_v71"

EXTRACTION_PATH = OUTPUT_DIR / "catia_full_extraction.json"
GAP_REPORT_PATH = OUTPUT_DIR / "com_gap_report.json"
VISUAL_FALLBACK_PATH = OUTPUT_DIR / "visual_fallback_report.json"

NONSEMANTIC_VISUAL_FIELDS = (
    "geometric_symbol",
    "displayed_tolerance_frame_content",
)


def json_safe(value: Any) -> Any:
    """Convert extracted data into JSON-compatible values."""
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


def is_present(value: Any) -> bool:
    """Treat zero and False as valid values."""
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True


def read_property(obj: Any, name: str) -> dict[str, Any]:
    """Read a COM property while preserving diagnostic information."""
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


def inventory_annotations(part: Any) -> dict[str, Any]:
    """Inventory CATIA annotation sets and annotations."""
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


def inventory_feature_tree(part: Any) -> dict[str, Any]:
    """Inventory CATIA bodies and their shapes."""
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


def run_extractor(
    function: Callable[..., Any],
    *args: Any,
) -> dict[str, Any]:
    """Run an extractor and preserve failures independently."""
    try:
        data = json_safe(function(*args))

        if isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict):
            count = len(data.get("parameters", []))
        else:
            count = None

        return {
            "status": "success",
            "count": count,
            "data": data,
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "count": None,
            "data": None,
            "error": repr(exc),
        }


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON and verify that the file can be reopened."""
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(json_safe(data), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with path.open("r", encoding="utf-8") as file:
        json.load(file)


def build_gap_report(
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Identify missing fields using the dedicated Gap Analyzer."""
    extractor_results = extraction["extractor_results"]
    nonsemantic = extractor_results.get("nonsemantic_gdt", {})

    annotations = (
        nonsemantic.get("data")
        if nonsemantic.get("status") == "success"
        else []
    )
    annotations = annotations or []

    required_fields: dict[str, list[str]] = {}
    extracted_data: dict[str, dict[str, Any]] = {}
    metadata: dict[str, dict[str, Any]] = {}

    for index, annotation in enumerate(annotations, start=1):
        if not isinstance(annotation, dict):
            continue

        name = (
            annotation.get("annotation_name")
            or f"Unknown annotation {index}"
        )
        annotation_id = f"nonsemantic_gdt:{name}"

        required_fields[annotation_id] = list(
            NONSEMANTIC_VISUAL_FIELDS
        )
        extracted_data[annotation_id] = annotation

        metadata[annotation_id] = {
            "annotation_name": name,
            "annotation_id": annotation_id,
            "extractor_family": "nonsemantic_gdt",
            "annotation_type": annotation.get(
                "annotation_type",
                "FTA_NonSemanticGDT",
            ),
            "known_metadata": {
                "super_type": annotation.get("super_type"),
                "tps_status": annotation.get("tps_status"),
                "surfaces": annotation.get("surfaces", []),
                "extraction_status": annotation.get(
                    "extraction_status"
                ),
            },
        }

    tasks = analyze_missing_fields(
        required_fields,
        extracted_data,
    )

    gaps = []

    for task in tasks:
        annotation_id = task["annotation_id"]

        gaps.append({
            **metadata[annotation_id],
            "missing_fields": task["missing_fields"],
            "status": task["status"],
            "next_action": (
                "Search matching OCR evidence or route the remaining "
                "missing fields to visual extraction."
            ),
            "engineering_approval": False,
        })

    failed_extractors = [
        {
            "extractor": name,
            "error": result.get("error"),
        }
        for name, result in extractor_results.items()
        if result.get("status") == "failed"
    ]

    return {
        "pipeline_version": "2.2-gap-analysis",
        "document": extraction["document"]["name"],
        "mode": "read_only",
        "counts": {
            "records_analyzed": len(required_fields),
            "records_requiring_review": len(gaps),
            "failed_extractors": len(failed_extractors),
        },
        "gaps": gaps,
        "failed_extractors": failed_extractors,
        "next_pipeline": "Dynamic visual fallback",
        "engineering_approval": False,
    }


def run_pipeline() -> dict[str, Any]:
    """Run CATIA extraction, gap analysis, and visual fallback."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    session = connect_to_catia()
    document = session.document
    part = document.Part

    print("\n====== PIPELINE 1: COM EXTRACTION ======")
    print("Document:", document.Name)

    tree_inventory = json_safe(inventory_annotations(part))
    feature_tree = json_safe(inventory_feature_tree(part))

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
        "pipeline_version": "2.2-com-extraction",
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

    write_json(EXTRACTION_PATH, extraction)

    gap_report = build_gap_report(extraction)
    write_json(GAP_REPORT_PATH, gap_report)

    print("\n====== GAP ANALYSIS ======")
    print("Annotations inventoried:", tree_inventory["annotation_count"])
    print("Records analyzed:", gap_report["counts"]["records_analyzed"])
    print(
        "Records requiring review:",
        gap_report["counts"]["records_requiring_review"],
    )
    print("Failed extractors:", gap_report["counts"]["failed_extractors"])

    for name, result in extractor_results.items():
        print(
            name,
            "| status:", result["status"],
            "| count:", result["count"],
        )
        if result["status"] == "failed":
            print("  Error:", result["error"])

    visual_fallback = run_visual_fallback(
        gap_report_path=GAP_REPORT_PATH,
        ocr_directory=OCR_REPORT_DIR,
        output_path=VISUAL_FALLBACK_PATH,
    )

    print("\n====== PIPELINE 2: VISUAL FALLBACK ======")
    print("Annotations reviewed:", visual_fallback["annotations_reviewed"])
    print("OCR reports discovered:", visual_fallback["ocr_reports_discovered"])

    for result in visual_fallback["results"]:
        print(
            result["annotation_name"],
            "| status:", result["status"],
            "| missing fields:", result["missing_fields"],
            "| OCR available:", result["ocr_report_available"],
        )

    print("\n====== OUTPUT FILES ======")
    print("Full extraction:", EXTRACTION_PATH.resolve())
    print("Gap report:", GAP_REPORT_PATH.resolve())
    print("Visual fallback:", VISUAL_FALLBACK_PATH.resolve())

    return extraction


if __name__ == "__main__":
    run_pipeline()
