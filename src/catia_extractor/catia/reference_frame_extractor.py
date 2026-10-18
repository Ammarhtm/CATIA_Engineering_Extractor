
from dataclasses import dataclass, asdict
from typing import Optional

import pythoncom


@dataclass
class ReferenceFrameResult:
    annotation_name: str
    primary: Optional[str]
    secondary: Optional[str]
    tertiary: Optional[str]


def read_frame(annotation):
    frame = annotation.ReferenceFrame()

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


def extract_reference_frames(part):
    results = []

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_ReferenceFrame":
                continue

            frame_data = read_frame(ann)

            result = ReferenceFrameResult(
                annotation_name=ann.Name,
                primary=frame_data["primary"],
                secondary=frame_data["secondary"],
                tertiary=frame_data["tertiary"],
            )

            results.append(asdict(result))

    return results
