
from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def test_referenceframe_signature():
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
                print("No associated reference frame")
                continue

            associated = resolve(ann.AssociatedRefFrame)

            info = associated._oleobj_.GetTypeInfo()
            attr = info.GetTypeAttr()

            for j in range(attr[6]):
                func = info.GetFuncDesc(j)
                names = info.GetNames(func[0])

                if names[0] == "ReferenceFrame":
                    print("Names:", names)
                    print("DISPID:", func[0])
                    print("Invoke kind:", func[4])
                    print("Parameter count:", func[6])
                    print("Return type:", func[8])
                    print("Full FUNCDESC:", func)
