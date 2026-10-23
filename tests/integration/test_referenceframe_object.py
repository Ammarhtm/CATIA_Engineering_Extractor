
import pythoncom
import win32com.client

from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def inspect_com(obj):
    try:
        info = obj._oleobj_.GetTypeInfo()
        attr = info.GetTypeAttr()

        print("COM GUID:", attr[0])
        print("Function count:", attr[6])

        for i in range(attr[6]):
            func = info.GetFuncDesc(i)
            names = info.GetNames(func[0])
            print(" ", names)

    except Exception as e:
        print("Inspection error:", repr(e))


def test_referenceframe_object():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_TruePosition":
                continue

            print(f"\n====== {ann.Name} ======")

            if not resolve(ann.IsAnAssociatedRefFrame):
                continue

            associated = resolve(ann.AssociatedRefFrame)

            raw = associated._oleobj_.InvokeTypes(
                1610940416,
                0,
                pythoncom.DISPATCH_PROPERTYGET,
                (pythoncom.VT_DISPATCH, 0),
                (),
            )

            frame = win32com.client.Dispatch(raw)

            print("ReferenceFrame object:", repr(frame))

            inspect_com(frame)

            print("\nBasic properties:")

            for prop in (
                "Name",
                "Type",
                "Count",
                "Item",
                "Reference",
                "Datums",
                "Datum",
            ):
                try:
                    value = getattr(frame, prop)

                    if callable(value):
                        print(prop, ": callable")
                    else:
                        print(prop, ":", repr(value))

                except Exception as e:
                    print(prop, ": unavailable", repr(e))
