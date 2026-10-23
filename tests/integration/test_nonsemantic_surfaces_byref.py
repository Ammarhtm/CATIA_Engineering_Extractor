
import pythoncom

from catia_extractor.catia.connection import connect_to_catia


def test_nonsemantic_surfaces_byref():
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

            count = int(ann.GetSurfacesCount())
            print("Surfaces count:", count)

            try:
                result = ann._oleobj_.InvokeTypes(
                    1610940467,
                    0,
                    pythoncom.DISPATCH_METHOD,
                    (pythoncom.VT_EMPTY, 0),
                    (
                        (
                            pythoncom.VT_BYREF
                            | pythoncom.VT_ARRAY
                            | pythoncom.VT_VARIANT,
                            3,
                        ),
                    ),
                    tuple([None] * count),
                )

                print("GetSurfaces result:", repr(result))
                print("Result type:", type(result))

                successful += 1

            except Exception as exc:
                print("GetSurfaces error:", repr(exc))

    print("\nAnnotations found:", found)
    print("Successful GetSurfaces:", successful)

    assert found == 2
