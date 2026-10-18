import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path("output/pipeline_v1/catia_inventory.json")

PROPERTIES = ("Name", "Type", "SuperType", "TPSStatus")


def read_property(obj, property_name):
    try:
        value = getattr(obj, property_name)

        if callable(value):
            value = value()

        if value is None or isinstance(value, (str, int, float, bool)):
            return {
                "status": "read_successfully",
                "value": value,
                "error": None,
            }

        return {
            "status": "read_successfully",
            "value": repr(value),
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "read_failed",
            "value": None,
            "error": repr(exc),
        }


def test_pipeline_json():
    session = connect_to_catia()
    document = session.document
    part = document.Part

    annotation_sets_data = []

    for set_index in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(set_index)

        try:
            set_name = annotation_set.Name
            set_name_status = "read_successfully"
            set_name_error = None
        except Exception as exc:
            set_name = None
            set_name_status = "read_failed"
            set_name_error = repr(exc)

        annotations_data = []

        for ann_index in range(
            1, annotation_set.Annotations.Count + 1
        ):
            annotation = annotation_set.Annotations.Item(ann_index)

            properties = {
                prop: read_property(annotation, prop)
                for prop in PROPERTIES
            }

            annotations_data.append({
                "index": ann_index,
                "name": properties["Name"]["value"],
                "type": properties["Type"]["value"],
                "parent": None,
                "properties": properties,
            })

        annotation_sets_data.append({
            "index": set_index,
            "name": set_name,
            "name_read_status": set_name_status,
            "name_read_error": set_name_error,
            "annotations": annotations_data,
        })

    total_annotations = sum(
        len(item["annotations"])
        for item in annotation_sets_data
    )

    report = {
        "pipeline_version": "1.0",
        "document": {
            "name": document.Name,
            "mode": "read_only",
        },
        "counts": {
            "annotation_sets": len(annotation_sets_data),
            "annotations": total_annotations,
        },
        "annotation_sets": annotation_sets_data,
        "notes": [
            "Parent relationships have not been extracted yet.",
            "Only the four tested properties are included.",
        ],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = json.loads(OUTPUT.read_text(encoding="utf-8"))

    assert loaded["document"]["name"] == document.Name
    assert loaded["counts"]["annotation_sets"] == 1
    assert loaded["counts"]["annotations"] == 11
    assert len(loaded["annotation_sets"][0]["annotations"]) == 11

    print("\n====== PIPELINE V1 JSON ======")
    print("Document:", loaded["document"]["name"])
    print("AnnotationSets:", loaded["counts"]["annotation_sets"])
    print("Annotations:", loaded["counts"]["annotations"])
    print("JSON valid:", True)
    print("Saved:", OUTPUT.resolve())
