
import unittest

from catia_extractor.catia.connection import connect_to_catia


def inspect_property(obj, name):
    try:
        value = getattr(obj, name)

        if callable(value):
            return "METHOD (not called)"

        return repr(value)

    except Exception as exc:
        return f"NOT ACCESSIBLE: {exc}"


class TestCATIAAnnotationDetails(unittest.TestCase):

    def test_annotation_details(self):
        session = connect_to_catia()

        part = session.document.Part
        annotation_sets = part.AnnotationSets

        print("\n========== FTA DETAILS ==========")

        for set_index in range(
            1, annotation_sets.Count + 1
        ):
            annotation_set = annotation_sets.Item(
                set_index
            )

            print(
                f"\nANNOTATION SET #{set_index}"
            )

            annotations = annotation_set.Annotations

            for index in range(
                1, annotations.Count + 1
            ):
                annotation = annotations.Item(index)

                print(
                    f"\n--- ANNOTATION {index} ---"
                )

                for attribute in (
                    "Name",
                    "Type",
                    "Text",
                    "Value",
                    "Tolerance",
                    "ToleranceValue",
                    "Datum",
                    "Reference",
                    "SuperType",
                    "IsDisplayed",
                ):
                    value = inspect_property(
                        annotation, attribute
                    )

                    print(
                        f"{attribute}: {value}"
                    )

        self.assertGreater(
            annotation_sets.Count, 0
        )


if __name__ == "__main__":
    unittest.main()
