
from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.catia.gdt_extractor import extract_gdt


def test_gdt_extractor():
    session = connect_to_catia()
    part = session.document.Part

    results = extract_gdt(part)

    for item in results:
        print(item)

    assert len(results) >= 2

    flatness = next(
        item for item in results
        if item["name"] == "Flatness.1"
    )

    position = next(
        item for item in results
        if item["name"] == "Position.1"
    )

    assert abs(flatness["tolerance_value"] - 0.02) < 1e-9
    assert abs(position["tolerance_value"] - 0.1) < 1e-9
