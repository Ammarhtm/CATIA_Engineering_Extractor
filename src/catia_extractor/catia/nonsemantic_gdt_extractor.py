
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

import pythoncom


@dataclass
class NonSemanticGDTResult:
    annotation_name: str
    annotation_type: str
    super_type: str
    tps_status: str
    surfaces: List[Any]
    extraction_status: str
    property_diagnostics: Dict[str, Dict[str, Any]]


def read_surfaces(annotation):
    count = int(annotation.GetSurfacesCount())

    if count == 0:
        return []

    result = annotation._oleobj_.InvokeTypes(
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

    return list(result)


def safe_read(obj, property_name, reader):
    """Read one property and preserve its success/failure evidence."""
    try:
        value = reader(obj)

        return value, {
            "status": "read_successfully",
            "value_type": type(value).__name__,
            "error": None,
        }

    except Exception as exc:
        return None, {
            "status": "read_failed",
            "value_type": None,
            "error": repr(exc),
        }


def extract_nonsemantic_gdt(part):
    results = []

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_NonSemanticGDT":
                continue

            name, name_diag = safe_read(
                ann, "Name", lambda obj: str(obj.Name)
            )

            ann_type, type_diag = safe_read(
                ann, "Type", lambda obj: str(obj.Type)
            )

            super_type, super_diag = safe_read(
                ann, "SuperType", lambda obj: str(obj.SuperType)
            )

            tps_status, tps_diag = safe_read(
                ann, "TPSStatus", lambda obj: str(obj.TPSStatus)
            )

            surfaces, surfaces_diag = safe_read(
                ann, "Surfaces", read_surfaces
            )

            diagnostics = {
                "name": name_diag,
                "type": type_diag,
                "super_type": super_diag,
                "tps_status": tps_diag,
                "surfaces": surfaces_diag,
            }

            failed = [
                key
                for key, detail in diagnostics.items()
                if detail["status"] == "read_failed"
            ]

            extraction_status = (
                "metadata_read_with_errors"
                if failed
                else "metadata_read_successfully"
            )

            result = NonSemanticGDTResult(
                annotation_name=name or f"Unknown annotation {i}",
                annotation_type=ann_type or "unknown",
                super_type=super_type or "unknown",
                tps_status=tps_status or "unknown",
                surfaces=surfaces if surfaces is not None else [],
                extraction_status=extraction_status,
                property_diagnostics=diagnostics,
            )

            results.append(asdict(result))

    return results
