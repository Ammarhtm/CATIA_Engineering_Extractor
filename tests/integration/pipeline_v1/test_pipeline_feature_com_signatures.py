
import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path(
    "output/pipeline_v1/feature_com_signatures.json"
)

TARGETS = {
    "Shaft.1": {"Sketch", "Parent", "Name"},
    "Hole.1": {
        "Sketch",
        "Parent",
        "Name",
        "Type",
        "BottomType",
        "HoleThreadDescription",
    },
}


def inspect_signatures(obj, target_names):
    result = {
        "guid": None,
        "members": [],
        "error": None,
    }

    try:
        info = obj._oleobj_.GetTypeInfo()
        attr = info.GetTypeAttr()
        result["guid"] = str(attr[0])

        for index in range(attr[6]):
            func = info.GetFuncDesc(index)
            names = info.GetNames(func[0])

            if not names:
                continue

            name = names[0]

            if name not in target_names:
                continue

            result["members"].append({
                "name": name,
                "dispid": func[0],
                "invkind": func[4],
                "parameters": repr(func[2]),
                "return_description": repr(func[1]),
            })

    except Exception as exc:
        result["error"] = repr(exc)

    return result


def test_pipeline_feature_com_signatures():
    session = connect_to_catia()
    part = session.document.Part

    results = []

    for body_index in range(1, part.Bodies.Count + 1):
        body = part.Bodies.Item(body_index)

        for shape_index in range(1, body.Shapes.Count + 1):
            shape = body.Shapes.Item(shape_index)
            name = str(shape.Name)

            if name not in TARGETS:
                continue

            results.append({
                "feature_name": name,
                "signature": inspect_signatures(
                    shape, TARGETS[name]
                ),
            })

    report = {
        "pipeline_version": "1.0-feature-com-signatures",
        "document": session.document.Name,
        "mode": "read_only",
        "results": results,
        "engineering_approval": False,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("Document:", session.document.Name)

    for item in results:
        print("\nFeature:", item["feature_name"])

        for member in item["signature"]["members"]:
            print(
                member["name"],
                "| DISPID:", member["dispid"],
                "| INVKIND:", member["invkind"],
                "| PARAMETERS:", member["parameters"],
            )

    print("Saved:", OUTPUT.resolve())

    assert len(results) == 2
    assert OUTPUT.exists()
