
from catia_extractor.catia.connection import connect_to_catia


def test_nonsemantic_metaobject():
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

            try:
                meta = ann.GetMetaObject()
                print("MetaObject:", repr(meta))

                if meta is None:
                    continue

                info = meta._oleobj_.GetTypeInfo()
                attr = info.GetTypeAttr()

                print("GUID:", attr[0])
                print("Functions:", attr[6])

                for index in range(attr[6]):
                    func = info.GetFuncDesc(index)
                    names = info.GetNames(func[0])

                    if names:
                        print(
                            names[0],
                            "| DISPID:",
                            func[0],
                        )

            except Exception as exc:
                print("GetMetaObject error:", repr(exc))

    assert found == 2
