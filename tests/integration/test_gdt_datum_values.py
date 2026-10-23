
from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def inspect_object(label, obj):
    print(f"\n{label}")
    print("Value:", repr(obj))
    print("Python type:", type(obj))

    if not hasattr(obj, "_oleobj_"):
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


def test_gdt_datum_values():
    session = connect_to_catia()
    part = session.document.Part

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

            # 1. Associated datum reference frame
            try:
                has_frame = resolve(
                    ann.IsAnAssociatedRefFrame
                )

                print("Has associated frame:", has_frame)

                if has_frame:
                    associated = resolve(
                        ann.AssociatedRefFrame
                    )

                    frame = resolve(
                        associated.ReferenceFrame
                    )

                    inspect_object(
                        "ReferenceFrame result", frame
                    )

            except Exception as e:
                print("ReferenceFrame error:", repr(e))

            # 2. Material condition modifier
            try:
                has_condition = resolve(
                    ann.HasAMaterialCondition
                )

                print(
                    "Has material condition:",
                    has_condition
                )

                if has_condition:
                    condition = resolve(
                        ann.MaterialCondition
                    )

                    modifier = resolve(
                        condition.Modifier
                    )

                    inspect_object(
                        "MaterialCondition.Modifier",
                        modifier
                    )

            except Exception as e:
                print("MaterialCondition error:", repr(e))
