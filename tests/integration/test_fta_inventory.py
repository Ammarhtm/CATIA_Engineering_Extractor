
from collections import Counter
from catia_extractor.catia.connection import connect_to_catia


def test_fta_inventory():
    session = connect_to_catia()
    part = session.document.Part

    counts = Counter()

    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        print(f"\n====== Annotation Set {s} ======")

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            name = ann.Name
            ann_type = ann.Type

            counts[ann_type] += 1

            print(f"{name} -> {ann_type}")

    print("\n====== FTA INVENTORY ======")

    for ann_type, count in sorted(counts.items()):
        print(f"{ann_type}: {count}")

    print("\nTOTAL:", sum(counts.values()))
