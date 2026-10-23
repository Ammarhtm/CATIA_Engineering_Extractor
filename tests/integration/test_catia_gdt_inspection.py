
from catia_extractor.catia.connection import connect_to_catia


def test_gdt_inspection():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if not any(
                x in ann.Name for x in ("Flatness", "Position")
            ):
                continue

            print(f"\n====== {ann.Name} ======")

            # Test 1: Python attributes
            print("\n[1] Python/COM attributes")
            try:
                for name in dir(ann):
                    if not name.startswith("_"):
                        print(" ", name)
            except Exception as e:
                print("dir() unavailable:", repr(e))

            # Test 2: COM TypeInfoCount
            print("\n[2] COM TypeInfoCount")
            try:
                count = ann._oleobj_.GetTypeInfoCount()
                print("TypeInfoCount:", count)
            except Exception as e:
                print("GetTypeInfoCount failed:", repr(e))

            # Test 3: COM TypeInfo
            print("\n[3] COM TypeInfo")
            try:
                info = ann._oleobj_.GetTypeInfo()
                attr = info.GetTypeAttr()

                print("Type GUID:", attr[0])
                print("Number of functions:", attr[6])

                for j in range(attr[6]):
                    try:
                        func = info.GetFuncDesc(j)
                        names = info.GetNames(func[0])
                        print(" ", names)
                    except Exception as e:
                        print("Function error:", repr(e))

            except Exception as e:
                print("GetTypeInfo failed:", repr(e))

            # Test 4: Known accessible properties
            print("\n[4] Basic properties")

            for prop in ("Name", "Type", "Visible"):
                try:
                    value = getattr(ann, prop)
                    print(f"{prop}: {value}")
                except Exception as e:
                    print(f"{prop}: unavailable ({e})")
