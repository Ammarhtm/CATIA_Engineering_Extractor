
from catia_extractor.catia.connection import connect_to_catia


def inspect_value(label, obj):
    print(f"\n{label}")
    print("Python type:", type(obj))
    print("Value:", repr(obj))

    if obj is None:
        return

    try:
        ole = obj._oleobj_
        info = ole.GetTypeInfo()
        attr = info.GetTypeAttr()

        print("COM GUID:", attr[0])
        print("Functions:", attr[6])

        for i in range(attr[6]):
            try:
                func = info.GetFuncDesc(i)
                names = info.GetNames(func[0])
                print(" ", names)
            except Exception as e:
                print("Function error:", repr(e))

    except Exception as e:
        print("No COM TypeInfo:", repr(e))


def test_tolerance_zone():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Name not in ("Flatness.1", "Position.1"):
                continue

            print(f"\n====== {ann.Name} ======")
            print("Type:", ann.Type)

            # Check whether the annotation has a tolerance zone
            try:
                value = ann.IsAToleranceZone
                if callable(value):
                    value = value()

                inspect_value("IsAToleranceZone", value)

            except Exception as e:
                print("IsAToleranceZone error:", repr(e))

            # Explore the tolerance zone object
            try:
                zone = ann.ToleranceZone
                if callable(zone):
                    zone = zone()

                inspect_value("ToleranceZone", zone)

            except Exception as e:
                print("ToleranceZone error:", repr(e))
