
from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def inspect_com(obj):
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


def test_linear_dimension_inspection():
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

                print("Dimension3D:", repr(dimension))
                inspect_com(dimension)

                for prop in (
                    "Name",
                    "Value",
                    "NominalValue",
                    "Tolerance",
                    "UpperTolerance",
                    "LowerTolerance",
                    "Unit",
                ):
                    try:
                        value = resolve(getattr(dimension, prop))
                        print(prop, ":", repr(value))
                    except Exception as e:
                        print(prop, "unavailable:", repr(e))

            except Exception as e:
                print("Dimension3D error:", repr(e))
