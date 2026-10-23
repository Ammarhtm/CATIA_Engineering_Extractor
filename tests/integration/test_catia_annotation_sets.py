
import unittest

from catia_extractor.catia.connection import connect_to_catia


def safe_get(obj, attr):
    try:
        return getattr(obj, attr), None
    except Exception as exc:
        return None, str(exc)


def inspect_collection(obj, attr):
    collection, error = safe_get(obj, attr)

    if collection is None:
        print(f"  {attr}: NON ACCESSIBLE ({error})")
        return

    count, count_error = safe_get(collection, "Count")

    if count_error:
        print(f"  {attr}: ACCESSIBLE (Count unavailable)")
        return

    print(f"  {attr}: Count = {count}")

    for index in range(1, min(count, 20) + 1):
        try:
            item = collection.Item(index)

            name, _ = safe_get(item, "Name")
            value, _ = safe_get(item, "Value")
            text, _ = safe_get(item, "Text")

            print(
                f"    [{index}] "
                f"Name={name!r}, "
                f"Value={value!r}, "
                f"Text={text!r}"
            )

        except Exception as exc:
            print(f"    [{index}] ERROR: {exc}")


class TestCATIAAnnotationSets(unittest.TestCase):

    def test_inspect_annotation_sets(self):
        session = connect_to_catia()
        part = session.document.Part
        annotation_sets = part.AnnotationSets

        print("\n=== CATIA FTA EXPLORATION ===")
        print("Document:", session.document_name)
        print("AnnotationSets:", annotation_sets.Count)

        for i in range(1, annotation_sets.Count + 1):
            annotation_set = annotation_sets.Item(i)

            print(f"\n--- AnnotationSet {i} ---")

            name, error = safe_get(annotation_set, "Name")
            print("Name:", name or error)

            for attr in (
                "Annotations",
                "AnnotationSets",
                "Captures",
                "TPSViews",
            ):
                inspect_collection(annotation_set, attr)

        self.assertGreaterEqual(annotation_sets.Count, 1)


if __name__ == "__main__":
    unittest.main()
