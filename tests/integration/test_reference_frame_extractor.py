
from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.catia.reference_frame_extractor import (
    extract_reference_frames,
)


def test_reference_frame_extractor():
    session = connect_to_catia()
    part = session.document.Part

    results = extract_reference_frames(part)

    print("\n====== REFERENCE FRAMES ======")

    for item in results:
        print(item)

    assert len(results) == 1

    frame = results[0]

    assert frame["annotation_name"] == "Datum Reference Frame.1"
    assert frame["primary"] == "A"
    assert frame["secondary"] == "B"
    assert frame["tertiary"] is None
