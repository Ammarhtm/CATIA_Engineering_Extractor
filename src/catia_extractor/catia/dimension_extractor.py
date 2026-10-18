
from dataclasses import dataclass, asdict
from typing import Optional

import pythoncom


@dataclass
class DimensionResult:
    annotation_name: str
    dimension_name: str
    dimension_type: int
    nominal_value: float
    tolerance_type: int
    tolerance_name: Optional[str]
    upper_tolerance: Optional[float]
    lower_tolerance: Optional[float]
    unit: Optional[str]


def resolve(value):
    return value() if callable(value) else value


def read_tolerances(dimension):
    arg_types = (
        (pythoncom.VT_BYREF | pythoncom.VT_I4, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_BSTR, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_R8, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_R8, 3),
        (pythoncom.VT_BYREF | pythoncom.VT_I4, 3),
    )

    return dimension._oleobj_.InvokeTypes(
        1610940450,
        0,
        pythoncom.DISPATCH_METHOD,
        (pythoncom.VT_EMPTY, 0),
        arg_types,
        0, "", "", "", 0.0, 0.0, 0,
    )


def extract_dimensions(part):
    results = []

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_LinearDimension":
                continue

            dimension3d = resolve(ann.Dimension3D)
            dimension2d = dimension3d.Get2dAnnot()
            value_obj = dimension2d.GetValue()

            nominal = float(resolve(value_obj.Value))

            (
                tol_type,
                tol_name,
                upper_text,
                lower_text,
                upper_numeric,
                lower_numeric,
                display_mode,
            ) = read_tolerances(dimension2d)

            has_numeric_tolerance = tol_type == 1

            result = DimensionResult(
                annotation_name=ann.Name,
                dimension_name=dimension2d.Name,
                dimension_type=int(dimension2d.DimType),
                nominal_value=nominal,
                tolerance_type=int(tol_type),
                tolerance_name=tol_name.strip() or None,
                upper_tolerance=(
                    float(upper_numeric)
                    if has_numeric_tolerance else None
                ),
                lower_tolerance=(
                    float(lower_numeric)
                    if has_numeric_tolerance else None
                ),
                unit=None,
            )

            results.append(asdict(result))

    return results
