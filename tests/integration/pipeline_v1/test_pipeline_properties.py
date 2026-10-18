
from catia_extractor.catia.connection import connect_to_catia


PROPERTIES = ("Name", "Type", "SuperType", "TPSStatus")


def safe_read(obj, property_name):
    try:
        value = getattr(obj, property_name)

        if callable(value):
            value = value()

        if value is None:
            return {
                "status": "read_successfully",
                "value": None,
                "error": None,
            }

        if isinstance(value, (str, int, float, bool)):
            serializable_value = value
        else:
            serializable_value = repr(value)

        return {
            "status": "read_successfully",
            "value": serializable_value,
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "read_failed",
            "value": None,
            "error": repr(exc),
        }


def test_pipeline_properties():
    session = connect_to_catia()
    part = session.document.Part

    results = []

    for set_index in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(set_index)

        for ann_index in range(
            1, annotation_set.Annotations.Count + 1
        ):
            ann = annotation_set.Annotations.Item(ann_index)

            property_results = {
                prop: safe_read(ann, prop)
                for prop in PROPERTIES
            }

            results.append({
                "annotation_name": property_results["Name"]["value"],
                "properties": property_results,
            })

    print("\n====== PIPELINE V1 PROPERTY TEST ======")
    print("Annotations inspected:", len(results))

    for item in results:
        print(f"\n--- {item['annotation_name']} ---")

        for prop, result in item["properties"].items():
            print(
                f"{prop}: {result['status']} | "
                f"value={result['value']!r}"
            )

            if result["error"]:
                print("  Error:", result["error"])

    assert results, "No annotations were inspected"

    print("\nProperty inspection: SUCCESS")
