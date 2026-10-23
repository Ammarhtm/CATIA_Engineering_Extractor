
import cv2
import numpy as np

from catia_extractor.vision.viewport_locator import (
    detect_viewport,
    draw_viewport_candidate,
)


def test_rejects_invalid_image():
    try:
        detect_viewport(None)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid image")


def test_empty_image_returns_review_status():
    image = np.zeros((0, 0, 3), dtype=np.uint8)

    result = detect_viewport(image)

    assert result["status"] == "needs_review"
    assert result["roi"] is None


def test_detects_strong_vertical_boundary():
    image = np.zeros((600, 1000, 3), dtype=np.uint8)

    # Simulate a tree/viewport separator.
    cv2.line(
        image,
        (300, 0),
        (300, 599),
        (255, 255, 255),
        3,
    )

    result = detect_viewport(
        image,
        min_boundary_strength=0.45,
    )

    assert result["boundary_x"] is not None
    assert result["roi"] is not None
    assert result["roi"][0] > result["boundary_x"]
    assert result["roi"][2] > 0


def test_draw_viewport_candidate_preserves_image_size():
    image = np.zeros((600, 1000, 3), dtype=np.uint8)

    result = {
        "status": "candidate",
        "roi": (310, 0, 690, 600),
        "boundary_x": 300,
    }

    preview = draw_viewport_candidate(image, result)

    assert preview.shape == image.shape


def test_uniform_image_requests_review():
    image = np.zeros((600, 1000, 3), dtype=np.uint8)

    result = detect_viewport(image)

    assert result["status"] == "needs_review"
    assert result["roi"] is None
