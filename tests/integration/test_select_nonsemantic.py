
from catia_extractor.catia.connection import connect_to_catia


def test_select_nonsemantic():
    session = connect_to_catia()
    document = session.document
    part = document.Part
    selection = document.Selection

    target_name = "Geometrical Tolerance.1"
    target = None

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Name == target_name:
                target = ann
                break

        if target is not None:
            break

    assert target is not None, f"Annotation introuvable: {target_name}"

    selection.Clear()
    selection.Add(target)

    assert selection.Count2 == 1

    print("\nSelected annotation:", target.Name)
    print("Selection type:", selection.Item2(1).Type)
    print("CATIA selection preserved for visual inspection")
