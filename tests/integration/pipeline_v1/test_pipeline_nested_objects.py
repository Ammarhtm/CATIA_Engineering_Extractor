
from pathlib import Path
import json

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path("output/pipeline_v1")
OUTPUT.mkdir(parents=True, exist_ok=True)

OBJECT_PROPERTIES = [
    "Dimension3D",
    "ToleranceZone",
    "ReferenceFrame",
    "AssociatedRefFrame",
]


def inspect_com_object(obj):
    """Inspect exposed COM type information without modifying CATIA."""
    if obj is None:
        return {
            "status": "empty",
            "methods": [],
        }

    try:
        ole = obj._oleobj_
        type_info = ole.GetTypeInfo()
        type_attr = type_info.GetTypeAttr()

        methods = []

        for index in range(type_attr[6]):
            try:
                func = type_info.GetFuncDesc(index)
                names = type_info.GetNames(func[0])

                if not names:
                    continue

                methods.append({
                    "name": names[0],
                    "dispid": func[0],
                    "parameter_count": len(func[2]),
                })

            except Exception as exc:
                methods.append({
                    "inspection_error": repr(exc),
                })

        return {
            "status": "type_info_read",
            "guid": str(type_attr[0]),
            "methods": methods,
        }

    except Exception as exc:
        return {
            "status": "inspection_failed",
            "error": repr(exc),
            "methods": [],
        }


def test_pipeline_nested_objects():
    session = connect_to_catia()
    part = session.document.Part

    report = {
        "pipeline_version": "1.3-nested-object-diagnostic",
        "document": session.document.Name,
        "mode": "read_only",
        "annotations": [],
    }

    for s in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(s)

        for i in range(1, annotation_set.Annotations.Count + 1):
            ann = annotation_set.Annotations.Item(i)

            entry = {
                "annotation_name": ann.Name,
                "annotation_type": ann.Type,
                "objects": {},
            }

            for property_name in OBJECT_PROPERTIES:
                try:
                    member = getattr(ann, property_name)
                    obj = member() if callable(member) else member

                    entry["objects"][property_name] = (
                        inspect_com_object(obj)
                    )

                except Exception as exc:
                    entry["objects"][property_name] = {
                        "status": "access_failed",
                        "error": repr(exc),
                        "methods": [],
                    }

            report["annotations"].append(entry)

    output_path = OUTPUT / "nested_objects.json"
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Report:", output_path.resolve())
    print("Annotations:", len(report["annotations"]))

    assert len(report["annotations"]) == 11
    assert output_path.exists()
