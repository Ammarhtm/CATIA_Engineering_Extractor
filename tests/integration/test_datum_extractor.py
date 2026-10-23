
from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.catia.datum_extractor import extract_datums


def test_datum_extractor():
    session = connect_to_catia()
    part = session.document.Part

    results = extract_datums(part)

    print("\n====== EXTRACTED DATUMS ======")

    for datum in results:
        print(datum)

    labels = {item["label"] for item in results}

    assert len(results) == 3
    assert labels == {"A", "B", "D"}
