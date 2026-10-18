
import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT_DIR = Path("output/pipeline_v1")
REPORT_PATH = OUTPUT_DIR / "pipeline_gap_report.json"

INPUT_FILES = {
    "full_extraction": OUTPUT_DIR / "catia_full_extraction.json",
    "inventory": OUTPUT_DIR / "catia_inventory.json",
    "gdt_objects": OUTPUT_DIR / "gdt_object_diagnostics.json",
    "gdt_text_access": OUTPUT_DIR / "gdt_text_access.json",
    "gdt_remaining_properties": (
        OUTPUT_DIR / "gdt_remaining_properties.json"
    ),
}


def load_json(path):
    if not path.exists():
        return None, f"File not found: {path}"

    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, repr(exc)


def find_nonsemantic_annotations(full, inventory):
    """Read annotations from the actual structures used by Pipeline 1."""
    found = []

    tree = full.get("tree_inventory", {})
    annotation_sets = tree.get("annotation_sets", [])

    if not annotation_sets:
        annotation_sets = inventory.get("annotation_sets", [])

    for annotation_set in annotation_sets:
        for annotation in annotation_set.get("annotations", []):
            properties = annotation.get("properties", {})

            name_data = properties.get("Name", {})
            type_data = properties.get("Type", {})

            name = name_data.get("value")
            annotation_type = type_data.get("value")

            if annotation_type == "FTA_NonSemanticGDT":
                found.append({
                    "annotation_name": name or "UNKNOWN",
                    "annotation_type": annotation_type,
                })

    # Fallback to the nonsemantic extractor if the tree is unavailable.
    if not found:
        result = full.get("extractor_results", {}).get(
            "nonsemantic_gdt", {}
        )

        if result.get("status") == "success":
            for annotation in result.get("data") or []:
                if annotation.get("annotation_type") == "FTA_NonSemanticGDT":
                    found.append({
                        "annotation_name": annotation.get(
                            "annotation_name", "UNKNOWN"
                        ),
                        "annotation_type": "FTA_NonSemanticGDT",
                    })

    # Avoid duplicate annotations without hiding distinct names.
    unique = {}
    for item in found:
        unique[item["annotation_name"]] = item

    return list(unique.values())


def main():
    session = connect_to_catia()
    document = session.document

    sources = {}
    source_errors = {}

    for key, path in INPUT_FILES.items():
        data, error = load_json(path)
        sources[key] = data

        if error:
            source_errors[key] = error

    full = sources["full_extraction"] or {}
    inventory = sources["inventory"] or {}

    annotations = find_nonsemantic_annotations(full, inventory)

    diagnostics = {
        key: sources[key]
        for key in (
            "gdt_objects",
            "gdt_text_access",
            "gdt_remaining_properties",
        )
        if sources[key] is not None
    }

    gaps = []

    for annotation in annotations:
        name = annotation["annotation_name"]

        gaps.append({
            "annotation_name": name,
            "annotation_type": annotation["annotation_type"],
            "com_metadata_available": True,
            "known_metadata": [
                "Name",
                "Type",
                "SuperType",
                "TPSStatus",
                "GetSurfacesCount",
                "GetSurfaces",
            ],
            "diagnostic_sources_loaded": list(diagnostics.keys()),
            "unresolved_items": [
                {
                    "item": "geometric_symbol",
                    "status": "not_extracted_by_current_com_tests",
                    "next_action": "Review visual extraction candidate",
                },
                {
                    "item": "displayed_tolerance_frame_content",
                    "status": "not_extracted_by_current_com_tests",
                    "next_action": "Review visual extraction candidate",
                },
            ],
            "engineering_approval": False,
        })

    report = {
        "pipeline_version": "1.8-com-gap-report",
        "document": document.Name,
        "mode": "read_only",
        "source_files": {
            key: str(path)
            for key, path in INPUT_FILES.items()
        },
        "source_errors": source_errors,
        "counts": {
            "source_files_expected": len(INPUT_FILES),
            "source_files_loaded": sum(
                value is not None for value in sources.values()
            ),
            "nonsemantic_gdt_annotations_reviewed": len(annotations),
            "annotations_requiring_visual_review": len(gaps),
        },
        "gaps": gaps,
        "next_pipeline": "OpenCV + OCR candidate review",
        "engineering_approval": False,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    saved = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    print("====== PIPELINE GAP REPORT ======")
    print("Document:", document.Name)
    print("Source files loaded:", saved["counts"]["source_files_loaded"])
    print(
        "GDT annotations reviewed:",
        saved["counts"]["nonsemantic_gdt_annotations_reviewed"],
    )
    print("Report:", REPORT_PATH.resolve())

    return saved


def test_pipeline_gap_report():
    main()


if __name__ == "__main__":
    main()
