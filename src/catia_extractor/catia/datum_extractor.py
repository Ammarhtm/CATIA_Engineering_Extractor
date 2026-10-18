
from dataclasses import dataclass, asdict


@dataclass
class DatumResult:
    annotation_name: str
    datum_name: str
    label: str


def resolve(value):
    return value() if callable(value) else value


def extract_datums(part):
    results = []

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Type != "FTA_DatumSimple":
                continue

            datum = resolve(ann.DatumSimple)

            result = DatumResult(
                annotation_name=ann.Name,
                datum_name=resolve(datum.Name),
                label=resolve(datum.Label),
            )

            results.append(asdict(result))

    return results
