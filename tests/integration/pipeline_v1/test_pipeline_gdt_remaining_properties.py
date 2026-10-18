import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path(
    "output/pipeline_v1/gdt_remaining_properties.json"
)

CANDIDATES = (
    "Name",
    "Type",
    "SuperType",
    "TPSStatus",
    "IsAToleranceZone",
    "IsAToleranceUnitBasisValue",
    "IsADefaultAnnotation",
    "HasATolerancePerUnitBasisRestrictiveValue",
    "IsAShiftedProfileTolerance",
    "IsACompositeTolerance",
    "IsAProjectedToleranceZone",
    "IsAnAssociatedRefFrame",
    "GetSurfacesCount",
)


def inspect_member(obj, name):
    try:
        member = getattr(obj, name)
        value = member() if callable(member) else member

        if value is None:
            return {
                "status": "success_empty",
                "value": None,
                "error": None,
            }

        if isinstance(value, (str, int, float, bool)):
            return {
                "status": "success",
                "value": value,
                "error": None,
            }

        return {
            "status": "object_returned",
            "value_type": type(value).__name__,
            "repr": repr(value),
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "value": None,
            "error": repr(exc),
        }


def list_com_methods(obj):
    try:
        info = obj._oleobj_.GetTypeInfo()
        attr = info.GetTypeAttr()
        methods = []

        for index in range(attr[6]):
            func = info.GetFuncDesc(index)
            names = info.GetNames(func[0])

            if names:
                methods.append(names[0])

        return {
            "status": "success",
            "methods": sorted(set(methods)),
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "methods": [],
            "error": repr(exc),
        }


def test_pipeline_gdt_remaining_properties():
    session = connect_to_catia()
    part = session.document.Part
    results = []

    for s in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(s)

        for i in range(1, annotation_set.Annotations.Count + 1):
            ann = annotation_set.Annotations.Item(i)

            if ann.Type != "FTA_NonSemanticGDT":
                continue

            results.append({
                "annotation_name": ann.Name,
                "annotation_type": ann.Type,
                "properties": {
                    name: inspect_member(ann, name)
                    for name in CANDIDATES
                },
                "com_interface": list_com_methods(ann),
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "pipeline_version": "1.6-gdt-remaining-properties",
                "document": session.document.Name,
                "mode": "read_only",
                "results": results,
                "engineering_approval": False,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n====== GDT REMAINING PROPERTIES ======")
    print("Document:", session.document.Name)
    print("Annotations inspected:", len(results))
    print("Report:", OUTPUT.resolve())

    assert len(results) == 2
    assert OUTPUT.exists()
