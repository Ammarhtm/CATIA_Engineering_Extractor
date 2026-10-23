
"""Unified CATIA COM inventory + saved V7.1 OCR candidates.

- Reads the active CATIA document.
- Uses existing COM extractors, including reference frames.
- Attaches saved V7.1 OCR candidates by annotation name.
- Does not rerun OCR or modify CATIA.
- Writes a separate JSON report.
"""

from pathlib import Path
import json

from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.catia.gdt_extractor import extract_gdt
from catia_extractor.catia.datum_extractor import extract_datums
from catia_extractor.catia.dimension_extractor import extract_dimensions
from catia_extractor.catia.nonsemantic_gdt_extractor import (
    extract_nonsemantic_gdt,
)
from catia_extractor.catia.reference_frame_extractor import (
    extract_reference_frames,
)


ROOT = Path(__file__).resolve().parents[2]

OCR_SUMMARY = (
    ROOT
    / "output"
    / "debug"
    / "nonsemantic_v71"
    / "pipeline_summary.json"
)

OUTPUT = (
    ROOT
    / "output"
    / "debug"
    / "unified_pipeline"
    / "pipeline_report.json"
)


def collect_extracted_names(
    gdt,
    datums,
    dimensions,
    nonsemantic,
    reference_frames,
):
    """Collect annotation names returned by existing extractors."""
    names = set()

    for item in gdt:
        name = item.get("name") or item.get("annotation_name")
        if name:
            names.add(str(name))

    for group in (
        datums,
        dimensions,
        nonsemantic,
        reference_frames,
    ):
        for item in group:
            name = item.get("annotation_name")
            if name:
                names.add(str(name))

    return names


def test_unified_pipeline_v71():
    # Read existing OCR results; do not rerun OCR.
    assert OCR_SUMMARY.is_file(), (
        f"V7.1 summary not found: {OCR_SUMMARY}"
    )

    ocr_data = json.loads(
        OCR_SUMMARY.read_text(encoding="utf-8")
    )

    ocr_by_name = {
        str(item["annotation"]): item
        for item in ocr_data.get("results", [])
        if item.get("annotation")
    }

    # Connect to the active CATIA document.
    session = connect_to_catia()
    document = session.document
    part = document.Part

    # Run the existing read-only extractors.
    gdt = extract_gdt(part)
    datums = extract_datums(part)
    dimensions = extract_dimensions(part)
    nonsemantic = extract_nonsemantic_gdt(part)
    reference_frames = extract_reference_frames(part)

    known_extracted = collect_extracted_names(
        gdt,
        datums,
        dimensions,
        nonsemantic,
        reference_frames,
    )

    inventory = []

    # Build inventory from the actual CATIA AnnotationSets.
    for s in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(s)

        for i in range(1, annotation_set.Annotations.Count + 1):
            annotation = annotation_set.Annotations.Item(i)

            name = str(annotation.Name)
            annotation_type = str(annotation.Type)

            com_covered = name in known_extracted
            ocr_result = ocr_by_name.get(name)

            if annotation_type == "FTA_NonSemanticGDT":
                if ocr_result is not None:
                    status = "OCR_CANDIDATE_NEEDS_VALIDATION"
                elif com_covered:
                    status = "COM_METADATA_ONLY_OCR_PENDING"
                else:
                    status = "NOT_EXTRACTED"
            elif com_covered:
                status = "COM_EXTRACTED_OR_METADATA"
            else:
                status = "NOT_EXTRACTED"

            inventory.append({
                "annotation_name": name,
                "annotation_type": annotation_type,
                "annotation_set": str(annotation_set.Name),
                "com_coverage": (
                    "EXTRACTED_OR_METADATA"
                    if com_covered
                    else "NOT_EXTRACTED"
                ),
                "ocr_fallback": ocr_result,
                "status": status,
            })

    total = len(inventory)

    counts = {
        "total_annotations": total,
        "com_extracted_or_metadata": sum(
            item["com_coverage"] == "EXTRACTED_OR_METADATA"
            for item in inventory
        ),
        "not_extracted": sum(
            item["status"] == "NOT_EXTRACTED"
            for item in inventory
        ),
        "ocr_candidates_attached": sum(
            item["ocr_fallback"] is not None
            for item in inventory
        ),
        "needs_validation": sum(
            item["status"] == "OCR_CANDIDATE_NEEDS_VALIDATION"
            for item in inventory
        ),
    }

    report = {
        "pipeline_version": "7.1-unified",
        "document": str(document.Name),
        "mode": "read_only",
        "counts": counts,
        "ocr_source": str(OCR_SUMMARY),
        "annotations": inventory,
        "reference_frames": reference_frames,
        "engineering_approval": False,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n====== UNIFIED PIPELINE V7.1 ======")
    print("Document:", document.Name)
    print(json.dumps(counts, indent=2, ensure_ascii=False))
    print("\n====== REFERENCE FRAMES ======")

    for frame in reference_frames:
        print(frame)

    print("\nReport:", OUTPUT)

    assert total > 0, "No CATIA annotations found"
    assert OUTPUT.is_file(), "Unified report was not created"
