
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


def test_extraction_inventory():
    # Connect to the existing CATIA session.
    session = connect_to_catia()
    part = session.document.Part

    # Run existing extractors.
    gdt = extract_gdt(part)
    datums = extract_datums(part)
    dimensions = extract_dimensions(part)
    nonsemantic = extract_nonsemantic_gdt(part)
    reference_frames = extract_reference_frames(part)

    # Inventory every annotation exposed by CATIA COM.
    all_annotations = []

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            all_annotations.append({
                "name": ann.Name,
                "type": ann.Type,
            })

    # Combine names reported by all extractors.
    extracted_names = (
        {item["name"] for item in gdt}
        | {item["annotation_name"] for item in datums}
        | {item["annotation_name"] for item in dimensions}
        | {item["annotation_name"] for item in nonsemantic}
        | {
            item["annotation_name"]
            for item in reference_frames
        }
    )

    print("\n====== EXTRACTION INVENTORY ======")
    print("Total annotations:", len(all_annotations))
    print("Semantic GDT:", len(gdt))
    print("Datums:", len(datums))
    print("Dimensions:", len(dimensions))
    print("Non-semantic GDT metadata:", len(nonsemantic))
    print("Reference frames:", len(reference_frames))

    print("\n====== ANNOTATION COVERAGE ======")

    for annotation in all_annotations:
        name = annotation["name"]

        status = (
            "EXTRACTED_OR_METADATA"
            if name in extracted_names
            else "NOT_EXTRACTED"
        )

        print(
            name,
            "|",
            annotation["type"],
            "|",
            status,
        )

    # Preserve the original inventory checks.
    assert len(all_annotations) == 11
    assert len(gdt) == 2
    assert len(datums) == 3
    assert len(dimensions) == 3
    assert len(nonsemantic) == 2
    assert len(reference_frames) == 1
