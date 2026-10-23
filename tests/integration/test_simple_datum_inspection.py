
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

        print(
            "Method:", names,
            "| DISPID:", func[0],
            "| Invoke kind:", func[4]
        )


def test_simple_datum_inspection():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_DatumSimple":
                continue

            print(f"\n====== {ann.Name} ======")

            try:
                datum = resolve(ann.DatumSimple)

                print("DatumSimple object:", repr(datum))
                inspect_com(datum)

                for prop in ("Name", "Value", "Label", "Text"):
                    try:
                        value = resolve(getattr(datum, prop))
                        print(prop, ":", repr(value))
                    except Exception as e:
                        print(prop, "unavailable:", repr(e))

            except Exception as e:
                print("DatumSimple error:", repr(e))
