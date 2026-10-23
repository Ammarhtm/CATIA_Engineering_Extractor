
from catia_extractor.catia.connection import connect_to_catia


def test_nonsemantic_material_condition():
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

            try:
                result = ann.HasAMaterialCondition()

                print(
                    "HasAMaterialCondition:",
                    repr(result),
                )

            except Exception as exc:
                print(
                    "HasAMaterialCondition error:",
                    repr(exc),
                )

    assert found == 2
