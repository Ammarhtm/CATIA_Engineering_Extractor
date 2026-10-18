
import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path(
    "output/pipeline_v1/feature_interfaces.json"
)

PROPERTY_NAMES = (
    "Name",
    "Type",
    "BottomType",
    "HoleThreadDescription",
    "Sketch",
    "Parent",
)


def read_property(obj, name):
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

        # Preserve useful information without
        # attempting to modify or resolve the object.
        object_info = {
            "python_type": type(value).__name__,
            "repr": repr(value),
        }

        try:
            object_info["name"] = str(value.Name)
        except Exception:
            pass

        return {
            "status": "object_returned",
            "value": object_info,
            "error": None,
        }

    except AttributeError as exc:
        return {
            "status": "not_available",
            "value": None,
            "error": repr(exc),
        }

    except Exception as exc:
        return {
            "status": "failed",
            "value": None,
            "error": repr(exc),
        }


def inspect_interface(obj):
    result = {
        "python_type": type(obj).__name__,
        "guid": None,
        "methods": [],
        "error": None,
    }

    try:
        info = obj._oleobj_.GetTypeInfo()
        attr = info.GetTypeAttr()
        result["guid"] = str(attr[0])

        for index in range(attr[6]):
            func = info.GetFuncDesc(index)
            names = info.GetNames(func[0])

            if names:
                result["methods"].append({
                    "name": names[0],
                    "dispid": func[0],
                    "kind": func[4],
                })

    except Exception as exc:
        result["error"] = repr(exc)

    return result


def test_pipeline_feature_interfaces():
    session = connect_to_catia()
    part = session.document.Part

    results = []

    for body_index in range(1, part.Bodies.Count + 1):
        body = part.Bodies.Item(body_index)

        for shape_index in range(
            1, body.Shapes.Count + 1
        ):
            shape = body.Shapes.Item(shape_index)

            properties = {}

            for property_name in PROPERTY_NAMES:
                properties[property_name] = read_property(
                    shape, property_name
                )

            results.append({
                "body_name": body.Name,
                "shape_name": shape.Name,
                "properties": properties,
                "interface": inspect_interface(shape),
            })

    report = {
        "pipeline_version": "1.1-feature-property-diagnostics",
        "document": session.document.Name,
        "mode": "read_only",
        "features": results,
        "engineering_approval": False,
    }

    OUTPUT.parent.mkdir(
        parents=True, exist_ok=True
    )

    OUTPUT.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    print("\n====== FEATURE PROPERTY DIAGNOSTICS ======")
    print("Document:", session.document.Name)
    print("Features inspected:", len(results))

    for item in results:
        print(f"\n--- {item['shape_name']} ---")

        for name, result in item["properties"].items():
            print(
                f"{name}: {result['status']} | "
                f"value={result['value']!r}"
            )

        print("COM GUID:", item["interface"]["guid"])

    print("\nSaved:", OUTPUT.resolve())

    assert len(results) == 2
    assert OUTPUT.exists()
