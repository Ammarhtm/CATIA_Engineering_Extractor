
from catia_extractor.catia.connection import connect_to_catia
import win32com.client
import pythoncom


def resolve(value):
    return value() if callable(value) else value


def inspect(label, obj):
    print(f"\n{label}: {repr(obj)}")

    if isinstance(obj, (str, int, float, bool, type(None))):
        return

    if not hasattr(obj, "_oleobj_"):
        return

    try:
        info = obj._oleobj_.GetTypeInfo()
        attr = info.GetTypeAttr()

        print("GUID:", attr[0])
        print("Functions:", attr[6])

        for j in range(attr[6]):
            func = info.GetFuncDesc(j)
            print(" ", info.GetNames(func[0]))

    except Exception as e:
        print("Inspection error:", repr(e))


def test_datum_frame_content():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_TruePosition":
                continue

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

            print("\n====== DATUM FRAME ======")
            print("Name:", frame.Name)
            print("Type:", frame.Type)

            for prop in ("Text", "ReferenceFrame"):
                try:
                    value = resolve(getattr(frame, prop))
                    inspect(prop, value)

                except Exception as e:
                    print(prop, "error:", repr(e))
