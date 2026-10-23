
import pythoncom

from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def test_datum_frame_values():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_ReferenceFrame":
                continue

            print(f"\n====== {ann.Name} ======")

            frame = resolve(ann.ReferenceFrame)

            # Frame has 3 BSTR pointer parameters
            # marked as IN | OUT in COM TypeInfo.
            arg_types = (
                (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
                (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
                (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
            )

            try:
                result = frame._oleobj_.InvokeTypes(
                    1610940416,
                    0,
                    pythoncom.DISPATCH_METHOD,
                    (pythoncom.VT_EMPTY, 0),
                    arg_types,
                    "",
                    "",
                    "",
                )

                print("Frame result:", repr(result))
                print("Python type:", type(result))

                if isinstance(result, tuple):
                    for index, value in enumerate(
                        result, start=1
                    ):
                        print(
                            f"Box {index}: {value!r}"
                        )

            except Exception as e:
                print("InvokeTypes error:", repr(e))
                raise
