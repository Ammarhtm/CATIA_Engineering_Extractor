
import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path("output/pipeline_v1")
OUTPUT.mkdir(parents=True, exist_ok=True)

# Read-only diagnostic: no setters, updates, or saves.
PROPERTY_NAMES = [
    "Name",
    "Type",
    "SuperType",
    "TPSStatus",
    "Text",
    "Noa",
    "ReferenceFrame",
    "DatumTarget",
    "ToleranceZone",
    "Dimension3D",
    "IsAToleranceZone",
    "IsAnAssociatedRefFrame",
    "IsAToleranceUnitBasisValue",
    "ToleranceUnitBasisValue",
    "IsADefaultAnnotation",
    "DefaultAnnotation",
    "AssociatedRefFrame",
    "TolerancePerUnitBasisRestrictiveValue",
    "ShiftedProfileTolerance",
    "CompositeTolerance",
    "ProjectedToleranceZone",
    "GetSurfacesCount",
]


def read_property(annotation, property_name):
    """Try reading a COM member and record its outcome."""
    try:
        member = getattr(annotation, property_name)

        # Some CATIA COM members are methods; others are properties.
        value = member() if callable(member) else member

        if value is None:
            status = "read_successfully_empty"
            serialized_value = None
        elif isinstance(value, (str, int, float, bool)):
            status = "read_successfully"
            serialized_value = value
        else:
            # Avoid serializing opaque COM objects as if their contents
            # had been extracted.
            status = "com_object_returned"
            serialized_value = {
                "python_type": type(value).__name__,
                "repr": repr(value),
            }

        return {
            "status": status,
            "value": serialized_value,
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "read_failed",
            "value": None,
            "error": repr(exc),
        }


def test_pipeline_properties_extended():
    session = connect_to_catia()
    document = session.document
    part = document.Part

    results = []

    for set_index in range(1, part.AnnotationSets.Count + 1):
        annotation_set = part.AnnotationSets.Item(set_index)

        for index in range(1, annotation_set.Annotations.Count + 1):
            annotation = annotation_set.Annotations.Item(index)

            properties = {
                name: read_property(annotation, name)
                for name in PROPERTY_NAMES
            }

            results.append({
                "annotation_name": annotation.Name,
                "annotation_type": annotation.Type,
                "annotation_set": f"Annotation Set.{set_index}",
                "properties": properties,
            })

    report = {
        "pipeline_version": "1.2-properties-diagnostic",
        "document": document.Name,
        "mode": "read_only",
        "annotation_count": len(results),
        "annotations": results,
        "engineering_approval": False,
    }

    output_path = OUTPUT / "extended_properties.json"
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n====== EXTENDED PROPERTY DIAGNOSTICS ======")
    print("Document:", document.Name)
    print("Annotations inspected:", len(results))
    print("Report:", output_path.resolve())

    assert results, "No annotations were inspected."
    assert output_path.exists()
