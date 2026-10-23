
from catia_extractor.catia.connection import connect_to_catia


def test_nonsemantic_selection():
    session = connect_to_catia()
    document = session.document
    part = document.Part

    selection = document.Selection
    found = 0

    try:
        for s in range(1, part.AnnotationSets.Count + 1):
            ann_set = part.AnnotationSets.Item(s)

            for i in range(1, ann_set.Annotations.Count + 1):
                ann = ann_set.Annotations.Item(i)

                if ann.Type != "FTA_NonSemanticGDT":
                    continue

                found += 1
                print(f"\n====== {ann.Name} ======")

                selection.Clear()
                selection.Add(ann)

                print("Selection Count2:", selection.Count2)

                if selection.Count2 > 0:
                    selected = selection.Item2(1)

                    print("Selected Type:", selected.Type)

                    try:
                        value = selected.Value
                        print("Selected Value:", repr(value))
                        print("Value Name:", value.Name)
                    except Exception as exc:
                        print("Value inspection:", repr(exc))

        assert found == 2

    finally:
        selection.Clear()
