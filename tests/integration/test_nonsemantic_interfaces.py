
from catia_extractor.catia.connection import connect_to_catia


def inspect_method(annotation, method_name):
    try:
        method = getattr(annotation, method_name)
        result = method()

        print(f"{method_name}: SUCCESS")
        print("  Result:", repr(result))
        print("  Python type:", type(result))

        if hasattr(result, "_oleobj_"):
            try:
                info = result._oleobj_.GetTypeInfo()
                attr = info.GetTypeAttr()

                print("  COM GUID:", attr[0])
                print("  COM functions:")

                for index in range(attr[6]):
                    func = info.GetFuncDesc(index)
                    names = info.GetNames(func[0])

                    if names:
                        print("   ", names[0])

            except Exception as exc:
                print("  TypeInfo error:", repr(exc))

    except Exception as exc:
        print(f"{method_name}: FAILED")
        print("  Error:", repr(exc))


def test_nonsemantic_interfaces():
    session = connect_to_catia()
    part = session.document.Part

    found = 0

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_NonSemanticGDT":
                continue

            found += 1

            print(f"\n====== {ann.Name} ======")
            print("Type:", ann.Type)
            print("SuperType:", ann.SuperType)

            inspect_method(ann, "ToleranceZone")
            inspect_method(ann, "Dimension3D")

    assert found == 2
