
import unittest

from catia_extractor.catia.connection import connect_to_catia


def safe_get(obj, attribute):
    try:
        return getattr(obj, attribute), None
    except Exception as exc:
        return None, str(exc)


def inspect_collection(obj, attribute):
    collection, error = safe_get(obj, attribute)

    if collection is None:
        print(f"{attribute}: NON ACCESSIBLE")
        if error:
            print("  Detail:", error)
        return

    count, count_error = safe_get(collection, "Count")

    if count_error:
        print(f"{attribute}: ACCESSIBLE, Count non disponible")
    else:
        print(f"{attribute}: ACCESSIBLE, Count = {count}")


class TestCATIAFTADiagnostic(unittest.TestCase):

    def test_fta_capabilities(self):
        session = connect_to_catia()
        document = session.document
        part = document.Part

        print("\n--- DOCUMENT ---")
        print("Name:", session.document_name)
        print("Type:", session.document_type)

        print("\n--- PART COLLECTIONS ---")
        for attribute in (
            "Bodies",
            "HybridBodies",
            "Parameters",
            "Relations",
            "AnnotationSets",
        ):
            inspect_collection(part, attribute)

        print("\n--- DOCUMENT COLLECTIONS ---")
        for attribute in (
            "AnnotationSets",
            "Selection",
        ):
            inspect_collection(document, attribute)

        print("\n--- FTA CHECK ---")
        annotations, error = safe_get(
            part, "AnnotationSets"
        )

        if annotations is not None:
            count, count_error = safe_get(
                annotations, "Count"
            )
            print("FTA collection accessible.")
            print("AnnotationSets Count:", count)
        else:
            print("FTA non accessible via Part.AnnotationSets")
            print("Detail:", error)

        self.assertEqual(
            session.document_type, "Part"
        )


if __name__ == "__main__":
    unittest.main()
