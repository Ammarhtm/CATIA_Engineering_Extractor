
import pytest

from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.catia.dimension_extractor import (
    extract_dimensions,
)


def test_dimension_extractor():
    session = connect_to_catia()
    part = session.document.Part

    results = extract_dimensions(part)

    print("\n====== EXTRACTED DIMENSIONS ======")

    for item in results:
        print(item)

    assert len(results) == 3

    by_name = {
        item["annotation_name"]: item
        for item in results
    }

    d1 = by_name["Linear Size.1"]
    d2 = by_name["Linear Size.2"]
    d3 = by_name["Linear Size.3"]

    assert d1["nominal_value"] == pytest.approx(19.96)
    assert d1["upper_tolerance"] == pytest.approx(0.03)
    assert d1["lower_tolerance"] == pytest.approx(-0.03)

    assert d2["nominal_value"] == pytest.approx(12.2)
    assert d2["upper_tolerance"] == pytest.approx(0.02)
    assert d2["lower_tolerance"] == pytest.approx(-0.02)

    assert d3["nominal_value"] == pytest.approx(30.0)
    assert d3["tolerance_type"] == 0
    assert d3["upper_tolerance"] is None
    assert d3["lower_tolerance"] is None
