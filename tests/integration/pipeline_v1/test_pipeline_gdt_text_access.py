
import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path("output/pipeline_v1/gdt_text_access.json")


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

        methods = []

        try:
            info = value._oleobj_.GetTypeInfo()
            attr = info.GetTypeAttr()

            for index in range(attr[6]):
                func = info.GetFuncDesc(index)
                names = info.GetNames(func[0])

                if names:
                    methods.append(names[0])

        except Exception:
            pass

        return {
            "status": "object_returned",
            "value_type": type(value).__name__,
            "repr": repr(value),
            "methods": methods,
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "value": None,
            "error": repr(exc),
        }


def test_pipeline_gdt_text_access():
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
                "properties": {
                    "Text": inspect_member(ann, "Text"),
                    "Noa": inspect_member(ann, "Noa"),
                    "Get2dAnnot": inspect_member(ann, "Get2dAnnot"),
                    "GetSurfacesCount": inspect_member(
                        ann, "GetSurfacesCount"
                    ),
                },
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "pipeline_version": "1.5-gdt-text-access",
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

    print("Report:", OUTPUT.resolve())
    print("Annotations inspected:", len(results))

    assert len(results) == 2
    assert OUTPUT.exists()
