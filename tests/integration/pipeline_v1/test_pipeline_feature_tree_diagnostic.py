
import json
from pathlib import Path

from catia_extractor.catia.connection import connect_to_catia


OUTPUT = Path(
    "output/pipeline_v1/feature_tree_diagnostic.json"
)


def safe_read(obj, property_name):
    try:
        member = getattr(obj, property_name)
        value = member() if callable(member) else member

        if isinstance(value, (str, int, float, bool)):
            return {
                "status": "success",
                "value": value,
                "error": None,
            }

        if value is None:
            return {
                "status": "success_empty",
                "value": None,
                "error": None,
            }

        return {
            "status": "object_returned",
            "value": repr(value),
            "python_type": type(value).__name__,
            "error": None,
        }

    except Exception as exc:
        return {
            "status": "failed",
            "value": None,
            "error": repr(exc),
        }


def test_pipeline_feature_tree_diagnostic():
    session = connect_to_catia()
    part = session.document.Part

    results = []

    for body_index in range(1, part.Bodies.Count + 1):
        body = part.Bodies.Item(body_index)

        body_result = {
            "body_name": safe_read(body, "Name"),
            "body_type": type(body).__name__,
            "shapes": [],
            "hybrid_bodies": [],
        }

        # Inspect the shapes exposed by each Body.
        try:
            shapes = body.Shapes

            for index in range(1, shapes.Count + 1):
                shape = shapes.Item(index)

                body_result["shapes"].append({
                    "index": index,
                    "name": safe_read(shape, "Name"),
                    "type": safe_read(shape, "ShapeType"),
                    "python_type": type(shape).__name__,
                })

        except Exception as exc:
            body_result["shapes_error"] = repr(exc)

        # Inspect HybridBodies without modifying the document.
        try:
            hybrid_bodies = body.HybridBodies

            for index in range(1, hybrid_bodies.Count + 1):
                hybrid = hybrid_bodies.Item(index)

                body_result["hybrid_bodies"].append({
                    "index": index,
                    "name": safe_read(hybrid, "Name"),
                    "python_type": type(hybrid).__name__,
                })

        except Exception as exc:
            body_result["hybrid_bodies_error"] = repr(exc)

        results.append(body_result)

    report = {
        "pipeline_version": "1.8-feature-tree-diagnostic",
        "document": session.document.Name,
        "mode": "read_only",
        "body_count": len(results),
        "bodies": results,
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

    print("====== FEATURE TREE DIAGNOSTIC ======")
    print("Document:", session.document.Name)
    print("Bodies inspected:", len(results))

    for body in results:
        print("\nBody:", body["body_name"])
        print("Shapes:", len(body["shapes"]))
        print("HybridBodies:", len(body["hybrid_bodies"]))

        for shape in body["shapes"]:
            print(
                " -",
                shape["name"],
                "| ShapeType:",
                shape["type"],
            )

    print("\nSaved:", OUTPUT.resolve())

    assert OUTPUT.exists()
    assert len(results) == part.Bodies.Count
