
from catia_extractor.catia.connection import connect_to_catia


def inspect_com_interface(obj):
    info = obj._oleobj_.GetTypeInfo()
    attr = info.GetTypeAttr()

    print("COM GUID:", attr[0])
    print("Total functions:", attr[6])

    for index in range(attr[6]):
        func = info.GetFuncDesc(index)
        names = info.GetNames(func[0])

        if not names:
            continue

        print(
            "Method:", names[0],
            "| DISPID:", func[0],
            "| Kind:", func[4],
            "| Params:", func[2],
        )


def test_default_annotation_interface():
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

                selected = selection.Item2(1)
                value = selected.Value

                print("Selected Type:", selected.Type)
                print("Selected Name:", value.Name)

                inspect_com_interface(value)

    finally:
        selection.Clear()

    assert found == 2
