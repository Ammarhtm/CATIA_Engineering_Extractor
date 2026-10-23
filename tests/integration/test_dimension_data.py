
import pythoncom

from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def inspect_value_object(obj):
    info = obj._oleobj_.GetTypeInfo()
    attr = info.GetTypeAttr()

    print("Value object GUID:", attr[0])

    for j in range(attr[6]):
        func = info.GetFuncDesc(j)
        names = info.GetNames(func[0])

        if j >= 17:
            print("  Method:", names)


def read_tolerances(dimension):
    # 7 paramètres COM IN | OUT
    arg_types = (
        (pythoncom.VT_BYREF | pythoncom.VT_I4, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_R8, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_R8, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_I4, 3),
    )

    return dimension._oleobj_.InvokeTypes(
        1610940450,
        0,
        pythoncom.DISPATCH_METHOD,
        (pythoncom.VT_EMPTY, 0),
        arg_types,
        0,
        "",
        "",
        "",
        0.0,
        0.0,
        0,
    )


def test_dimension_data():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_LinearDimension":
                continue

            print(f"\n====== {ann.Name} ======")

            dimension3d = resolve(ann.Dimension3D)
            dimension2d = dimension3d.Get2dAnnot()

            print("2D Name:", dimension2d.Name)
            print("DimType:", dimension2d.DimType)

            try:
                value_obj = dimension2d.GetValue()
                inspect_value_object(value_obj)

                for prop in (
                    "Value",
                    "Name",
                    "Unit",
                    "DisplayValue",
                ):
                    try:
                        value = resolve(getattr(value_obj, prop))
                        print(prop, ":", repr(value))
                    except Exception as e:
                        print(prop, "unavailable:", repr(e))

            except Exception as e:
                print("Value error:", repr(e))

            try:
                tolerances = read_tolerances(dimension2d)

                print("\nTolerances:", repr(tolerances))

                if isinstance(tolerances, tuple):
                    labels = (
                        "TolType",
                        "TolName",
                        "UpperText",
                        "LowerText",
                        "UpperNumeric",
                        "LowerNumeric",
                        "DisplayMode",
                    )

                    for label, value in zip(
                        labels, tolerances
                    ):
                        print(label, ":", repr(value))

            except Exception as e:
                print("Tolerance error:", repr(e))
