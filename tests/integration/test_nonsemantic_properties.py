
from catia_extractor.catia.connection import connect_to_catia


def resolve(value):
    return value() if callable(value) else value


def safe_read(obj, property_name):
    try:
        value = resolve(getattr(obj, property_name))
        print(f"{property_name}: {value!r}")
        return value
    except Exception as exc:
        print(f"{property_name} ERROR: {exc!r}")
        return None


def test_nonsemantic_properties():
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

            safe_read(ann, "SuperType")
            safe_read(ann, "TPSStatus")

            has_zone = safe_read(
                ann, "IsAToleranceZone"
            )

            if has_zone is True:
                zone = safe_read(
                    ann, "ToleranceZone"
                )

                if zone is not None:
                    safe_read(zone, "Value")
                    safe_read(zone, "Form")

            has_frame = safe_read(
                ann, "IsAnAssociatedRefFrame"
            )

            if has_frame is True:
                print(
                    "Associated reference frame detected"
                )

            safe_read(ann, "GetSurfacesCount")

    assert found == 2, (
        f"Expected 2 annotations, found {found}"
    )
