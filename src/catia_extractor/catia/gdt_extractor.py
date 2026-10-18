
from dataclasses import dataclass, asdict
from typing import Optional
import pythoncom
import win32com.client


@dataclass
class GDTResult:
    name: str
    gdt_type: str
    tolerance_value: Optional[float]
    tolerance_form: Optional[str]
    material_modifier: Optional[str]
    datum_reference_frame: Optional[dict]


def resolve(value):
    return value() if callable(value) else value


def read_datum_frame(annotation):
    if not resolve(annotation.IsAnAssociatedRefFrame):
        return None

    associated = resolve(annotation.AssociatedRefFrame)

    raw = associated._oleobj_.InvokeTypes(
        1610940416,
        0,
        pythoncom.DISPATCH_PROPERTYGET,
        (pythoncom.VT_DISPATCH, 0),
        (),
    )

    frame_annotation = win32com.client.Dispatch(raw)
    frame = resolve(frame_annotation.ReferenceFrame)

    arg_types = (
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
    )

    values = frame._oleobj_.InvokeTypes(
        1610940416,
        0,
        pythoncom.DISPATCH_METHOD,
        (pythoncom.VT_EMPTY, 0),
        arg_types,
        "",
        "",
        "",
    )

    return {
        "primary": values[0] or None,
        "secondary": values[1] or None,
        "tertiary": values[2] or None,
    }


def read_material_modifier(annotation):
    if not resolve(annotation.HasAMaterialCondition):
        return None

    condition = resolve(annotation.MaterialCondition)
    modifier = resolve(condition.Modifier)

    if modifier == "No Modifier":
        return None

    return modifier


def extract_gdt(part):
    results = []

    supported_types = {
        "FTA_Flatness",
        "FTA_TruePosition",
    }

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            try:
                gdt_type = ann.Type

                if gdt_type not in supported_types:
                    continue

                value = None
                form = None

                if resolve(ann.IsAToleranceZone):
                    zone = resolve(ann.ToleranceZone)
                    value = resolve(zone.Value)
                    form = resolve(zone.Form)

                result = GDTResult(
                    name=ann.Name,
                    gdt_type=gdt_type,
                    tolerance_value=value,
                    tolerance_form=form,
                    material_modifier=read_material_modifier(ann),
                    datum_reference_frame=read_datum_frame(ann),
                )

                results.append(asdict(result))

            except Exception as e:
                print(f"Extraction failed for {ann.Name}: {e}")

    return results
