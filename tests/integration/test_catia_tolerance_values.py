
from catia_extractor.catia.connection import connect_to_catia


def test_tolerance_values():
    session = connect_to_catia()
    part = session.document.Part

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Name not in ("Flatness.1", "Position.1"):
                continue

            print(f"\n====== {ann.Name} ======")
            print("Annotation type:", ann.Type)

            try:
                has_zone = ann.IsAToleranceZone
                if callable(has_zone):
                    has_zone = has_zone()

                if not has_zone:
                    print("No tolerance zone")
                    continue

                zone = ann.ToleranceZone
                if callable(zone):
                    zone = zone()

                print("ToleranceZone object:", repr(zone))

            except Exception as e:
                print("ToleranceZone access failed:", repr(e))
                continue

            for prop in ("Value", "Form"):
                try:
                    result = getattr(zone, prop)

                    if callable(result):
                        result = result()

                    print(f"{prop}: {result!r}")
                    print(f"{prop} Python type: {type(result)}")

                except Exception as e:
                    print(f"{prop} error: {repr(e)}")
