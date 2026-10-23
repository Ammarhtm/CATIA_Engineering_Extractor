
from catia_extractor.catia.connection import connect_to_catia


def test_nonsemantic_position():
    session = connect_to_catia()
    document = session.document
    part = document.Part

    spa = document.GetWorkbench("SPAWorkbench")
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

                try:
                    reference = part.CreateReferenceFromObject(ann)
                    print("Reference:", repr(reference))

                    measurable = spa.GetMeasurable(reference)
                    print("Measurable:", repr(measurable))

                    coords = measurable.GetPoint()
                    print("Coordinates:", coords)

                except Exception as exc:
                    print("Position unavailable:", repr(exc))

    finally:
        selection.Clear()

    assert found == 2
