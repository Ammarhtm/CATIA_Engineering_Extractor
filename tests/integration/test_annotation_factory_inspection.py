
from catia_extractor.catia.connection import connect_to_catia


def inspect_com(obj):
    info = obj._oleobj_.GetTypeInfo()
    attr = info.GetTypeAttr()

    print("GUID:", attr[0])
    print("Total functions:", attr[6])

    for index in range(17, attr[6]):
        func = info.GetFuncDesc(index)
        names = info.GetNames(func[0])

        print(
            "Method:", names,
            "| DISPID:", func[0],
            "| Kind:", func[4],
            "| Params:", func[2],
        )


def test_annotation_factory_inspection():
    session = connect_to_catia()
    part = session.document.Part

    set_count = int(part.AnnotationSets.Count)
    assert set_count >= 1

    for s in range(1, set_count + 1):
        ann_set = part.AnnotationSets.Item(s)

        print(f"\n====== {ann_set.Name} ======")

        try:
            factory = ann_set.AnnotationFactory

            print(
                "AnnotationFactory:",
                repr(factory),
            )

            inspect_com(factory)

        except Exception as exc:
            print(
                "AnnotationFactory error:",
                repr(exc),
            )
