
import cv2
import numpy as np
import pytest

from catia_extractor.vision.selection_guided_locator import (
    locate_selected_annotation_frame,
)


def make_frame_image():
    image = np.zeros((300, 600, 3), dtype=np.uint8)

    cv2.rectangle(
        image,
        (200, 120),
        (320, 150),
        (255, 255, 255),
        2,
    )

    return image


def test_rejects_invalid_images():
    with pytest.raises(ValueError):
        locate_selected_annotation_frame(None, None)


def test_rejects_different_image_shapes():
    before = np.zeros((200, 300, 3), dtype=np.uint8)
    after = np.zeros((300, 300, 3), dtype=np.uint8)

    with pytest.raises(ValueError):
        locate_selected_annotation_frame(before, after)


def test_no_selection_change_does_not_claim_association():
    image = make_frame_image()

    result = locate_selected_annotation_frame(
        image,
        image.copy(),
    )

    assert result["status"] == "no_reliable_selection_change"
    assert result["candidates"] == []
    assert result["engineering_approval"] is False


def test_selection_change_returns_diagnostic_report():
    before = make_frame_image()
    after = before.copy()

    # Simulate a CATIA orange selection highlight on the frame.
    cv2.line(
        after,
        (200, 135),
        (320, 135),
        (255, 140, 0),
        3,
    )

    result = locate_selected_annotation_frame(
        before,
        after,
    )

    assert result["selection_evidence_available"] is True
    assert result["selected_pixel_count"] >= 3
    assert result["status"] in {
        "selection_overlap_candidates_found",
        "candidates_without_selection_overlap",
        "no_frame_candidates",
    }
    assert result["engineering_approval"] is False


def test_roi_is_forwarded_to_frame_detection():
    image = make_frame_image()

    # The ROI does not contain the frame, so no frame should be found.
    before = image.copy()
    after = image.copy()

    cv2.line(
        after,
        (200, 135),
        (320, 135),
        (255, 140, 0),
        3,
    )

    result = locate_selected_annotation_frame(
        before,
        after,
        roi=(0, 0, 100, 100),
    )

    assert result["roi"] == (0, 0, 100, 100)
    assert result["candidates"] == []
    assert result["status"] == "no_frame_candidates"
