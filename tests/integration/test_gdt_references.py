
from catia_extractor.catia.connection import connect_to_catia


def inspect_com_object(obj):
    if not hasattr(obj, "_oleobj_"):
        print("Value:", repr(obj))
        return

    try:
        info = obj._oleobj_.GetTypeInfo()
        attr = info.GetTypeAttr()

        print("COM GUID:", attr[0])

        for i in range(attr[6]):
            func = info.GetFuncDesc(i)
            names = info.GetNames(func[0])
            print(" ", names)

    except Exception as e:
        print("Inspection error:", repr(e))


def test_gdt_references():
    session = connect_to_catia()
    part = session.document.Part

    properties = [
        "ReferenceFrame",
        "IsAnAssociatedRefFrame",
        "AssociatedRefFrame",
        "HasAMaterialCondition",
        "MaterialCondition",
    ]

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type not in (
                "FTA_Flatness",
                "FTA_TruePosition",
            ):
                continue

            print(f"\n====== {ann.Name} ======")

            for prop in properties:
                print(f"\n--- {prop} ---")

                try:
                    value = getattr(ann, prop)

                    if callable(value):
                        value = value()

                    inspect_com_object(value)

                except Exception as e:
                    print("Unavailable:", repr(e))
