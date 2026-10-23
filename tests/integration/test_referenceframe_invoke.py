
import pythoncom

from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def test_referenceframe_invoke():
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
                print("No associated frame")
                continue

            associated = resolve(ann.AssociatedRefFrame)

            dispid = 1610940416

            print("Testing direct COM invocation")

            for return_type in (
                pythoncom.VT_DISPATCH,
                pythoncom.VT_UNKNOWN,
                pythoncom.VT_VARIANT,
            ):
                try:
                    result = associated._oleobj_.InvokeTypes(
                        dispid,
                        0,
                        pythoncom.DISPATCH_PROPERTYGET,
                        (return_type, 0),
                        (),
                    )

                    print(
                        f"SUCCESS return_type={return_type}:",
                        repr(result)
                    )

                    if hasattr(result, "_oleobj_"):
                        info = result._oleobj_.GetTypeInfo()
                        attr = info.GetTypeAttr()

                        print("Returned GUID:", attr[0])

                        for j in range(attr[6]):
                            func = info.GetFuncDesc(j)
                            print(
                                " ",
                                info.GetNames(func[0])
                            )

                except Exception as e:
                    print(
                        f"FAILED return_type={return_type}:",
                        repr(e)
                    )
