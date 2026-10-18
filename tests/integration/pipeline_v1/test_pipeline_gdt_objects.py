
import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path("output/pipeline_v1/gdt_object_diagnostics.json")


def read_member(obj, name):
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
            "value": {
                "python_type": type(value).__name__,
                "repr": repr(value),
            },
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "value": None,
            "error": repr(exc),
        }


def test_pipeline_gdt_objects():
    session = connect_to_catia()
    part = session.document.Part

    results = []

    for s in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(s)

        for i in range(1, annotation_set.Annotations.Count + 1):
            ann = annotation_set.Annotations.Item(i)

            if ann.Type != "FTA_NonSemanticGDT":
                continue

            entry = {
                "annotation_name": ann.Name,
                "annotation_type": ann.Type,
                "properties": {},
            }

            for name in (
                "IsAToleranceZone",
                "ToleranceZone",
                "Dimension3D",
                "IsAnAssociatedRefFrame",
                "AssociatedRefFrame",
            ):
                entry["properties"][name] = read_member(ann, name)

            # Inspect nested objects only when CATIA returns them.
            for name in ("ToleranceZone", "Dimension3D"):
                result = entry["properties"][name]

                if result["status"] != "object_returned":
                    continue

                try:
                    member = getattr(ann, name)
                    obj = member() if callable(member) else member

                    nested = {}

                    for nested_name in (
                        "Value",
                        "Form",
                        "Get2dAnnot",
                    ):
                        nested[nested_name] = read_member(
                            obj, nested_name
                        )

                    entry["properties"][f"{name}_details"] = nested

                except Exception as exc:
                    entry["properties"][f"{name}_details"] = {
                        "status": "failed",
                        "error": repr(exc),
                    }

            results.append(entry)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "pipeline_version": "1.4-gdt-object-diagnostics",
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

    print("\n====== GDT OBJECT DIAGNOSTICS ======")
    print("Document:", session.document.Name)
    print("GDT annotations:", len(results))
    print("Report:", OUTPUT.resolve())

    assert len(results) == 2
    assert OUTPUT.exists()
