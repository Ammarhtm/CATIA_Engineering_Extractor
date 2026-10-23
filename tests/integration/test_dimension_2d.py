
from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def inspect_com(obj):
    if not hasattr(obj, "_oleobj_"):
        print("Not a COM dispatch object")
        return

    info = obj._oleobj_.GetTypeInfo()
    attr = info.GetTypeAttr()

    print("GUID:", attr[0])
    print("Function count:", attr[6])

    for j in range(attr[6]):
        func = info.GetFuncDesc(j)
        names = info.GetNames(func[0])

        if j < 17:
            continue

        print(
            "Method:", names,
            "| DISPID:", func[0],
            "| Invoke kind:", func[4]
        )


def test_dimension_2d():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_LinearDimension":
                continue

            print(f"\n====== {ann.Name} ======")

            try:
                dimension = resolve(ann.Dimension3D)

                annot2d = dimension.Get2dAnnot()

                print("Get2dAnnot result:", repr(annot2d))
                print("Python type:", type(annot2d))

                if annot2d is None:
                    print("No 2D annotation returned")
                    continue

                inspect_com(annot2d)

                for prop in (
                    "Name",
                    "Type",
                    "Value",
                    "Text",
                    "Dimension",
                ):
                    try:
                        value = getattr(annot2d, prop)

                        if callable(value):
                            print(prop, ": callable")
                        else:
                            print(prop, ":", repr(value))

                    except Exception as e:
                        print(prop, "unavailable:", repr(e))

            except Exception as e:
                print("Get2dAnnot error:", repr(e))
