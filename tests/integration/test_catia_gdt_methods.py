from catia_extractor.catia.connection import connect_to_catia


def test_gdt_methods():

    session = connect_to_catia()

    part = session.document.Part
    ann_set = part.AnnotationSets.Item(1)

    for i in range(1, ann_set.Annotations.Count + 1):

        ann = ann_set.Annotations.Item(i)

        if "Position" in ann.Name or "Flatness" in ann.Name:

            print("\n======", ann.Name, "======")

            print("COM object:", ann._oleobj_)

            print("\nTry common methods:")

            methods = [
                "GetValue",
                "GetTolerance",
                "GetSymbol",
                "GetText",
                "GetReference",
                "GetDatum",
                "GetTechnologicalObject",
                "GetGeometry",
                "GetSpecification"
            ]

            for m in methods:
                try:
                    getattr(ann, m)
                    print("✅", m, "FOUND")
                except Exception:
                    print("❌", m, "NO")


if __name__ == "__main__":
    test_gdt_methods()