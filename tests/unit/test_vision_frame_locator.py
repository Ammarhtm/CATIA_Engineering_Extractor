
def test_roi_returns_candidates_in_full_image_coordinates():
    import cv2
    import numpy as np

    from catia_extractor.vision.frame_locator import (
        detect_frame_geometry,
    )

    image = np.zeros((500, 800, 3), dtype=np.uint8)

    # Frame inside the ROI, at full-image position (350, 200).
    cv2.rectangle(
        image,
        (350, 200),
        (490, 235),
        (255, 255, 255),
        2,
    )

    _, candidates = detect_frame_geometry(
        image,
        roi=(300, 150, 300, 150),
    )

    assert candidates
    x, y, width, height = candidates[0]["box"]

    assert 340 <= x <= 355
    assert 190 <= y <= 205
    assert width > 0
    assert height > 0


def test_roi_outside_image_returns_no_candidates():
    import numpy as np

    from catia_extractor.vision.frame_locator import (
        detect_frame_geometry,
    )

    image = np.zeros((200, 300, 3), dtype=np.uint8)

    _, candidates = detect_frame_geometry(
        image,
        roi=(500, 500, 100, 100),
    )

    assert candidates == []
