from catia_extractor.catia.connection import connect_to_catia


def test_fta_text():

    session = connect_to_catia()

    print("SESSION:", session)

    doc = session.document

    part = doc.Part

    ann_set = part.AnnotationSets.Item(1)

    for i in range(1, ann_set.Annotations.Count + 1):

        ann = ann_set.Annotations.Item(i)

        print("\n---", ann.Name, "---")

        try:
            print("TEXT:", ann.Text())
        except Exception as e:
            print("TEXT ERROR:", e)


if __name__ == "__main__":
    test_fta_text()