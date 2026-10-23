
from catia_extractor.catia.connection import connect_to_catia


KEYWORDS = (
    "graphic",
    "visual",
    "text",
    "display",
    "frame",
    "view",
    "annot",
    "component",
    "symbol",
    "tolerance",
    "noa",
    "representation",
    "leader",
    "dress",
    "get",
)


def inspect_interface(obj, label):
    print(f"\n--- {label} ---")

    try:
        info = obj._oleobj_.GetTypeInfo()
        attr = info.GetTypeAttr()

        print("GUID:", attr[0])
        print("Functions:", attr[6])

        for index in range(attr[6]):
            func = info.GetFuncDesc(index)
            names = info.GetNames(func[0])

            if not names:
                continue

            name = names[0]

            if any(
                keyword in name.lower()
                for keyword in KEYWORDS
            ):
                print(
                    "Name:", name,
                    "| DISPID:", func[0],
                    "| Kind:", func[4],
                    "| Params:", func[2],
                )

    except Exception as exc:
        print("Inspection error:", repr(exc))


def test_nonsemantic_graphic_interfaces():
    session = connect_to_catia()
    part = session.document.Part

    found = 0

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        inspect_interface(
            ann_set,
            f"AnnotationSet {s}",
        )

        inspect_interface(
            ann_set.TPSViews,
            "TPSViews collection",
        )

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_NonSemanticGDT":
                continue

            found += 1

            inspect_interface(
                ann,
                ann.Name,
            )

    assert found == 2
