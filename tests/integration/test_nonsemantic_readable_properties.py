
from catia_extractor.catia.connection import connect_to_catia


METHODS = [
    "Text",
    "Noa",
    "ReferenceFrame",
    "DatumTarget",
    "IsAToleranceZone",
    "IsAToleranceUnitBasisValue",
    "ToleranceUnitBasisValue",
    "IsADefaultAnnotation",
    "DefaultAnnotation",
    "IsAnAssociatedRefFrame",
    "AssociatedRefFrame",
]


def test_nonsemantic_readable_properties():
    session = connect_to_catia()
    part = session.document.Part
    found = 0

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_NonSemanticGDT":
                continue

            found += 1
            print(f"\n====== {ann.Name} ======")

            for name in METHODS:
                try:
                    member = getattr(ann, name)

                    if callable(member):
                        try:
                            value = member()
                        except TypeError:
                            value = "<requires arguments>"
                    else:
                        value = member

                    print(f"{name}: {value!r}")

                except Exception as exc:
                    print(f"{name}: FAILED - {exc!r}")

    assert found == 2
