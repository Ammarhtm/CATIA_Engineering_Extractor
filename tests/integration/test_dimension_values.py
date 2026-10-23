
from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def test_dimension_values():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_LinearDimension":
                continue

            print(f"\n====== {ann.Name} ======")

            dimension3d = resolve(ann.Dimension3D)
            dimension2d = dimension3d.Get2dAnnot()

            print("2D Name:", dimension2d.Name)

            try:
                print("DimType:", resolve(dimension2d.DimType))
            except Exception as e:
                print("DimType error:", repr(e))

            try:
                value = dimension2d.GetValue()
                print("GetValue result:", repr(value))
                print("Python type:", type(value))
            except Exception as e:
                print("GetValue error:", repr(e))

            info = dimension2d._oleobj_.GetTypeInfo()
            attr = info.GetTypeAttr()

            for j in range(attr[6]):
                func = info.GetFuncDesc(j)
                names = info.GetNames(func[0])

                if names[0] in ("GetValue", "GetTolerances"):
                    print("\nMethod:", names)
                    print("DISPID:", func[0])
                    print("Invoke kind:", func[4])
                    print("Full FUNCDESC:", func)
