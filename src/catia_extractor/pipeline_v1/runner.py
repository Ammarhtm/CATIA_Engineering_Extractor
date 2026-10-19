
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
from catia_extractor.pipelines.visual_fallback import (
    run_visual_fallback,
)


ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = ROOT / "output" / "pipeline_v1"

OCR_REPORT_DIR = (
    ROOT / "output" / "debug" / "nonsemantic_v71"
)

EXTRACTION_PATH = OUTPUT_DIR / "catia_full_extraction.json"
GAP_REPORT_PATH = OUTPUT_DIR / "com_gap_report.json"
VISUAL_FALLBACK_PATH = OUTPUT_DIR / "visual_fallback_report.json"


# These fields are not supplied by the current nonsemantic COM extractor.
# If a future COM extractor supplies them, the gap analysis will preserve
# the extracted values instead of scheduling them for visual extraction.
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

    if value is None or isinstance(
        value, (str, int, float, bool)
    ):
        return value

    return repr(value)


def is_present(value: Any) -> bool:
    """Check whether a field has a usable extracted value.

    Numeric zero and boolean False are valid values.
    """
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
    """Inventory annotation sets without modifying the CATIA document."""
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
    """Inventory bodies and shapes."""
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
    """Run one extractor and preserve its success or failure."""
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


def build_gap_report(
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """Identify missing visual fields from actual COM extraction records."""
    extractor_results = extraction["extractor_results"]
    nonsemantic = extractor_results.get("nonsemantic_gdt", {})

    annotations = (
        nonsemantic.get("data")
        if nonsemantic.get("status") == "success"
        else []
    )

    gaps = []

    for index, annotation in enumerate(annotations or [], start=1):
        if not isinstance(annotation, dict):
            continue

        name = (
            annotation.get("annotation_name")
            or f"Unknown annotation {index}"
        )

        annotation_type = annotation.get(
            "annotation_type",
            "FTA_NonSemanticGDT",
        )

        # Build a list dynamically: only fields with no usable COM
        # value are sent to the visual fallback stage.
        missing_fields = [
            field
            for field in NONSEMANTIC_VISUAL_FIELDS
            if not is_present(annotation.get(field))
        ]

        if not missing_fields:
            continue

        gaps.append({
            "annotation_name": name,
            "annotation_id": (
                f"nonsemantic_gdt:{name}"
            ),
            "extractor_family": "nonsemantic_gdt",
            "annotation_type": annotation_type,
            "known_metadata": {
                "super_type": annotation.get("super_type"),
                "tps_status": annotation.get("tps_status"),
                "surfaces": annotation.get("surfaces", []),
                "extraction_status": annotation.get(
                    "extraction_status"
                ),
            },
            "missing_fields": missing_fields,
            "status": "pending_visual_extraction",
            "next_action": (
                "Search for matching OCR evidence or route only "
                "the remaining missing fields to visual extraction"
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
        "pipeline_version": "2.1-gap-analysis",
        "document": extraction["document"]["name"],
        "mode": "read_only",
        "counts": {
            "records_analyzed": len(annotations or []),
            "records_requiring_review": len(gaps),
            "failed_extractors": len(failed_extractors),
        },
        "gaps": gaps,
        "failed_extractors": failed_extractors,
        "next_pipeline": "Dynamic visual fallback",
        "engineering_approval": False,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Save and validate a JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Confirm that the saved file can be reopened.
    json.loads(path.read_text(encoding="utf-8"))


def run_pipeline() -> dict[str, Any]:
    """Run COM extraction, gap analysis, then visual fallback."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Stage 1: Connect to the currently available CATIA session.
    session = connect_to_catia()
    document = session.document
    part = document.Part

    print("\n====== PIPELINE 1: COM EXTRACTION ======")
    print("Document:", document.Name)

    # Stage 2: Collect inventory and run the existing COM extractors.
    tree_inventory = inventory_annotations(part)
    feature_tree = inventory_feature_tree(part)

    extractor_results = {
        "part_parameters_and_features": run_extractor(
            read_catia_part, session
        ),
        "semantic_gdt": run_extractor(
            extract_gdt, part
        ),
        "datums": run_extractor(
            extract_datums, part
        ),
        "dimensions": run_extractor(
            extract_dimensions, part
        ),
        "nonsemantic_gdt": run_extractor(
            extract_nonsemantic_gdt, part
        ),
        "reference_frames": run_extractor(
            extract_reference_frames, part
        ),
    }

    extraction = {
        "pipeline_version": "2.1-com-extraction",
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

    # Stage 3: Compare the COM results with the visual fields required.
    gap_report = build_gap_report(extraction)
    write_json(GAP_REPORT_PATH, gap_report)

    print("\n====== GAP ANALYSIS ======")
    print(
        "Annotations inventoried:",
        tree_inventory["annotation_count"],
    )
    print(
        "Nonsemantic records analyzed:",
        gap_report["counts"]["records_analyzed"],
    )
    print(
        "Records requiring review:",
        gap_report["counts"]["records_requiring_review"],
    )
    print(
        "Failed extractors:",
        gap_report["counts"]["failed_extractors"],
    )

    for name, result in extractor_results.items():
        print(
            name,
            "| status:", result["status"],
            "| count:", result.get("count"),
        )

        if result["status"] == "failed":
            print("  Error:", result["error"])

    # Stage 4: Enrich the gaps with existing OCR candidates.
    # No OCR report is treated as engineering approval.
    visual_report = run_visual_fallback(
        gap_report_path=GAP_REPORT_PATH,
        ocr_directory=OCR_REPORT_DIR,
        output_path=VISUAL_FALLBACK_PATH,
    )

    print("\n====== PIPELINE 2: VISUAL FALLBACK ======")
    print(
        "Annotations reviewed:",
        visual_report["annotations_reviewed"],
    )
    print(
        "OCR reports discovered:",
        visual_report["ocr_reports_discovered"],
    )

    for item in visual_report["results"]:
        print(
            item["annotation_name"],
            "| status:", item["status"],
            "| missing fields:", item["missing_fields"],
            "| OCR available:", item["ocr_report_available"],
        )

    print("\n====== OUTPUT FILES ======")
    print("Full extraction:", EXTRACTION_PATH.resolve())
    print("Gap report:", GAP_REPORT_PATH.resolve())
    print("Visual fallback:", VISUAL_FALLBACK_PATH.resolve())

    return {
        "extraction": extraction,
        "gap_report": gap_report,
        "visual_fallback_report": visual_report,
        "engineering_approval": False,
    }


if __name__ == "__main__":
    run_pipeline()
