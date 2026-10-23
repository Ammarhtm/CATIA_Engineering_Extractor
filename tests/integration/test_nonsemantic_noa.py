
from catia_extractor.catia.connection import connect_to_catia


def inspect_com(obj):
    info = obj._oleobj_.GetTypeInfo()
    attr = info.GetTypeAttr()

    print("GUID:", attr[0])
    print("Function count:", attr[6])

    for j in range(17, attr[6]):
        func = info.GetFuncDesc(j)
        names = info.GetNames(func[0])

        print(
            "Method:", names,
            "| DISPID:", func[0],
            "| Invoke kind:", func[4],
            "| Parameters:", func[2],
        )


def test_nonsemantic_noa():
    session = connect_to_catia()
    part = session.document.Part

    found = 0
    successful = 0

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_NonSemanticGDT":
                continue

            found += 1
            print(f"\n====== {ann.Name} ======")

            try:
                noa = ann.Noa()

                print("Noa result:", repr(noa))
                print("Python type:", type(noa))

                if hasattr(noa, "_oleobj_"):
                    inspect_com(noa)
                    successful += 1

            except Exception as exc:
                print("Noa error:", repr(exc))

    print("\nAnnotations found:", found)
    print("Noa objects accessible:", successful)

    assert found == 2
