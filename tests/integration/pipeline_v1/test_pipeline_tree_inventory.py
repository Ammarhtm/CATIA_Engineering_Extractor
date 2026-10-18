from catia_extractor.catia.connection import connect_to_catia


def test_pipeline_tree_inventory():
    session = connect_to_catia()
    document = session.document
    part = document.Part

    inventory = []

    annotation_sets = part.AnnotationSets
    set_count = int(annotation_sets.Count)

    for set_index in range(1, set_count + 1):
        annotation_set = annotation_sets.Item(set_index)

        set_name = getattr(annotation_set, "Name", None)

        node = {
            "annotation_set_name": set_name,
            "annotation_set_index": set_index,
            "annotations": [],
        }

        annotations = annotation_set.Annotations
        annotation_count = int(annotations.Count)

        for annotation_index in range(1, annotation_count + 1):
            annotation = annotations.Item(annotation_index)

            try:
                name = annotation.Name
                name_error = None
            except Exception as exc:
                name = None
                name_error = repr(exc)

            try:
                annotation_type = annotation.Type
                type_error = None
            except Exception as exc:
                annotation_type = None
                type_error = repr(exc)

            node["annotations"].append({
                "index": annotation_index,
                "name": name,
                "type": annotation_type,
                "parent": None,
                "read_errors": {
                    "name": name_error,
                    "type": type_error,
                },
            })

        inventory.append(node)

    total_annotations = sum(
        len(item["annotations"]) for item in inventory
    )

    print("\n====== PIPELINE V1 TREE INVENTORY ======")
    print("Document:", document.Name)
    print("AnnotationSets:", len(inventory))
    print("Annotations:", total_annotations)

    for item in inventory:
        print(f"\n--- {item['annotation_set_name']} ---")

        for annotation in item["annotations"]:
            print(
                f"{annotation['index']}. "
                f"{annotation['name']} | "
                f"{annotation['type']}"
            )

    assert len(inventory) > 0, "No AnnotationSets found"
    assert total_annotations > 0, "No Annotations found"

    print("\nTree inventory: SUCCESS")
