from pathlib import Path

import cv2
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "debug" / "nonsemantic_v51"
OUTPUT.mkdir(parents=True, exist_ok=True)

# Replace these paths with the clean, full CATIA screenshots
# produced by Version 5 (before selection / debug overlays).
SOURCES = {
    "Geometrical Tolerance.1": {
        "image": ROOT / "output" / "debug" / "nonsemantic_v5"
                 / "Geometrical_Tolerance_1_before.png",
        # Seed from V5 green box, for the 974x1039 screenshot.
        # This is only a regression fixture, not a universal coordinate.
        "seed": (323, 724, 68, 32),
    },
    "Geometrical Tolerance.2": {
        "image": ROOT / "output" / "debug" / "nonsemantic_v5"
                 / "Geometrical_Tolerance_2_before.png",
        "seed": (507, 590, 88, 32),
    },
}


def make_line_masks(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # CATIA annotations are bright on a dark background.
    bright = cv2.inRange(gray, 145, 255)

    horizontal = cv2.morphologyEx(
        bright,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)),
    )

    vertical = cv2.morphologyEx(
        bright,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, 8)),
    )

    return horizontal, vertical


def expand_frame(image, seed):
    horizontal, vertical = make_line_masks(image)
    height, width = horizontal.shape

    x, y, w, h = seed
    cx = x + w // 2
    cy = y + h // 2

    # Limit search to a local neighborhood of the seed.
    # This reduces accidental merging with other annotations.
    pad_x = max(35, int(w * 1.2))
    pad_y = max(12, int(h * 0.7))

    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(width, x + w + pad_x)
    y2 = min(height, y + h + pad_y)

    h_roi = horizontal[y1:y2, x1:x2]
    v_roi = vertical[y1:y2, x1:x2]

    # Find horizontal frame borders close to the seed.
    row_lengths = np.count_nonzero(h_roi, axis=1)
    min_row_length = max(18, int(w * 0.45))

    candidate_rows = np.where(
        row_lengths >= min_row_length
    )[0]

    if len(candidate_rows) < 2:
        return None, "horizontal borders not found"

    # Prefer borders around the seed center.
    rows_above = [
        int(r) for r in candidate_rows
        if y1 + r < cy
    ]
    rows_below = [
        int(r) for r in candidate_rows
        if y1 + r > cy
    ]

    if not rows_above or not rows_below:
        return None, "cannot bracket seed vertically"

    top = y1 + max(rows_above)
    bottom = y1 + min(rows_below)

    if bottom - top < 8:
        return None, "frame height too small"

    # Identify vertical dividers and outer borders.
    band = vertical[
        max(0, top):min(height, bottom + 1),
        x1:x2,
    ]

    col_lengths = np.count_nonzero(band, axis=0)
    min_col_length = max(6, int((bottom - top) * 0.45))

    candidate_cols = np.where(
        col_lengths >= min_col_length
    )[0]

    if len(candidate_cols) < 2:
        return None, "vertical borders not found"

    cols = sorted(set(x1 + int(c) for c in candidate_cols))

    # Expand to nearby vertical lines, including adjacent cells.
    left_candidates = [c for c in cols if c <= x]
    right_candidates = [c for c in cols if c >= x + w - 1]

    if not left_candidates or not right_candidates:
        return None, "outer frame borders not found"

    left = min(left_candidates)
    right = max(right_candidates)

    if right - left < w:
        return None, "expanded frame narrower than seed"

    return (left, top, right - left + 1, bottom - top + 1), None


@pytest.mark.parametrize(
    "name",
    list(SOURCES),
)
def test_nonsemantic_frame_expansion_v51(name):
    source = SOURCES[name]
    image_path = source["image"]

    assert image_path.exists(), (
        f"Clean screenshot not found: {image_path}\n"
        "Update SOURCES['image'] with the actual V5 before screenshot."
    )

    image = cv2.imread(str(image_path))
    assert image is not None, f"Cannot read {image_path}"

    box, error = expand_frame(image, source["seed"])

    print(f"\n====== {name} ======")
    print("Seed:", source["seed"])
    print("Expanded:", box)
    print("Error:", error)

    debug = image.copy()
    x, y, w, h = source["seed"]

    cv2.rectangle(
        debug,
        (x, y),
        (x + w, y + h),
        (0, 255, 255),
        2,
    )

    if box is not None:
        fx, fy, fw, fh = box

        cv2.rectangle(
            debug,
            (fx, fy),
            (fx + fw, fy + fh),
            (0, 255, 0),
            2,
        )

        crop = image[fy:fy + fh, fx:fx + fw]

        cv2.imwrite(
            str(OUTPUT / f"{name.replace(' ', '_')}_crop.png"),
            crop,
        )

    cv2.imwrite(
        str(OUTPUT / f"{name.replace(' ', '_')}_debug.png"),
        debug,
    )

    assert box is not None, (
        f"Frame expansion failed for {name}: {error}"
    )

    # Expansion should include more than the seed.
    assert box[2] > source["seed"][2], (
        "Frame was not expanded horizontally"
    )