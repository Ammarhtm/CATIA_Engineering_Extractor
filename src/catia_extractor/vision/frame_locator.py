
"""Vision frame locator V2.

Detects rectangular GD&T frame candidates in RGB images.

Features:
- Deduplicates overlapping contour detections.
- Supports an optional region of interest (ROI).
- Preserves full-image coordinates when an ROI is supplied.
- Ranks candidates using geometric evidence.
- Uses selection-mask overlap as supporting evidence only.
- Never claims that a candidate belongs to an annotation without
  sufficient evidence.

This module does not perform OCR or engineering validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


VERSION = "2.0"


def _validate_rgb_image(rgb_image: Any) -> None:
    """Validate an RGB image without requiring a non-empty image."""
    if (
        rgb_image is None
        or not isinstance(rgb_image, np.ndarray)
        or rgb_image.ndim != 3
        or rgb_image.shape[2] != 3
    ):
        raise ValueError(
            "Expected an RGB NumPy array with shape (height, width, 3)."
        )


def _geometry_strength(candidate: dict[str, Any]) -> float:
    """Score visible horizontal and vertical frame-line evidence."""
    horizontal = candidate.get("horizontal_rows", 0)
    vertical = candidate.get("vertical_cols", 0)

    horizontal_score = min(max(horizontal / 2.0, 0.0), 1.0)
    vertical_score = min(max(vertical / 3.0, 0.0), 1.0)

    return 0.5 * horizontal_score + 0.5 * vertical_score


def _intersection_over_smaller(box_a, box_b) -> float:
    """Measure overlap relative to the smaller rectangle."""
    ax, ay, aw, ah = map(int, box_a)
    bx, by, bw, bh = map(int, box_b)

    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)

    intersection = max(0, right - left) * max(0, bottom - top)

    area_a = max(0, aw) * max(0, ah)
    area_b = max(0, bw) * max(0, bh)
    smaller_area = min(area_a, area_b)

    if smaller_area == 0:
        return 0.0

    return intersection / smaller_area


def _deduplicate_candidates(
    candidates: list[dict[str, Any]],
    overlap_threshold: float = 0.80,
) -> list[dict[str, Any]]:
    """Merge duplicate detections, keeping the strongest geometry.

    Candidates are duplicates when one rectangle substantially covers
    the other. Different-sized frames that merely touch or partially
    overlap remain separate candidates.

    The function is deterministic and preserves the selected
    candidate's original metadata.
    """
    if not 0.0 < overlap_threshold <= 1.0:
        raise ValueError("overlap_threshold must be in (0, 1].")

    ordered = sorted(
        candidates,
        key=lambda item: (
            _geometry_strength(item),
            item.get("horizontal_rows", 0)
            + item.get("vertical_cols", 0),
            item["box"][2] * item["box"][3],
        ),
        reverse=True,
    )

    kept: list[dict[str, Any]] = []

    for candidate in ordered:
        duplicate_index = None

        for index, existing in enumerate(kept):
            overlap = _intersection_over_smaller(
                candidate["box"],
                existing["box"],
            )

            if overlap >= overlap_threshold:
                duplicate_index = index
                break

        if duplicate_index is None:
            kept.append(candidate)
            continue

        # Replace only when the new candidate has stronger geometric
        # evidence. Sorting normally makes this unnecessary, but the
        # comparison protects future callers with modified ordering.
        existing = kept[duplicate_index]

        if _geometry_strength(candidate) > _geometry_strength(existing):
            kept[duplicate_index] = candidate

    return kept


def detect_frame_geometry(
    rgb_image,
    roi: tuple[int, int, int, int] | None = None,
    min_width: int = 30,
    max_width: int = 350,
    min_height: int = 10,
    max_height: int = 90,
    min_aspect: float = 1.5,
    max_aspect: float = 20.0,
    deduplicate: bool = True,
):
    """Detect plausible rectangular frames in an RGB screenshot.

    Args:
        rgb_image: Full RGB image.
        roi: Optional (x, y, width, height) search region in full-image
            coordinates. Returned candidate boxes remain in full-image
            coordinates.
        min_width, max_width: Candidate width limits.
        min_height, max_height: Candidate height limits.
        min_aspect, max_aspect: Width-to-height ratio limits.
        deduplicate: Remove overlapping duplicate detections.

    Returns:
        (line_mask, candidates)

        line_mask has the same height and width as the full image.
        Candidate boxes use (x, y, width, height).
    """
    _validate_rgb_image(rgb_image)

    if min_width <= 0 or min_height <= 0:
        raise ValueError("Minimum dimensions must be positive.")

    if max_width < min_width or max_height < min_height:
        raise ValueError("Maximum dimensions must be >= minimum dimensions.")

    if min_aspect <= 0 or max_aspect < min_aspect:
        raise ValueError("Invalid aspect ratio limits.")

    full_height, full_width = rgb_image.shape[:2]
    full_mask = np.zeros((full_height, full_width), dtype=np.uint8)

    if full_height == 0 or full_width == 0:
        return full_mask, []

    if roi is None:
        offset_x, offset_y = 0, 0
        image = rgb_image
    else:
        if len(roi) != 4:
            raise ValueError("ROI must be (x, y, width, height).")

        x, y, width, height = map(int, roi)

        if width <= 0 or height <= 0:
            raise ValueError("ROI width and height must be positive.")

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(full_width, x + width)
        y2 = min(full_height, y + height)

        if x2 <= x1 or y2 <= y1:
            return full_mask, []

        offset_x, offset_y = x1, y1
        image = rgb_image[y1:y2, x1:x2]

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    bright = cv2.inRange(gray, 145, 255)

    horizontal = cv2.morphologyEx(
        bright,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(
            cv2.MORPH_RECT, (12, 1)
        ),
    )

    vertical = cv2.morphologyEx(
        bright,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(
            cv2.MORPH_RECT, (1, 8)
        ),
    )

    lines = cv2.bitwise_or(horizontal, vertical)

    joined = cv2.morphologyEx(
        lines,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(
            cv2.MORPH_RECT, (3, 3)
        ),
    )

    contours, _ = cv2.findContours(
        joined,
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    image_height, image_width = gray.shape
    candidates: list[dict[str, Any]] = []

    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)

        if not (
            min_width <= width <= min(max_width, image_width)
        ):
            continue

        if not min_height <= height <= max_height:
            continue

        aspect = width / max(height, 1)

        if not min_aspect <= aspect <= max_aspect:
            continue

        # Ignore detections that touch the image boundary: these are
        # frequently fragments of clipped interface elements.
        if x <= 0 or y <= 0:
            continue

        if x + width >= image_width or y + height >= image_height:
            continue

        horizontal_roi = horizontal[y:y + height, x:x + width]
        vertical_roi = vertical[y:y + height, x:x + width]

        horizontal_rows = int(
            np.count_nonzero(
                np.count_nonzero(horizontal_roi, axis=1)
                >= 0.35 * width
            )
        )

        vertical_cols = int(
            np.count_nonzero(
                np.count_nonzero(vertical_roi, axis=0)
                >= 0.35 * height
            )
        )

        # A plausible frame should contain evidence of both horizontal
        # and vertical strokes. This is a geometric filter, not proof
        # of annotation identity.
        if horizontal_rows < 1 or vertical_cols < 1:
            continue

        candidates.append({
            "box": (
                int(x + offset_x),
                int(y + offset_y),
                int(width),
                int(height),
            ),
            "aspect": round(float(aspect), 3),
            "horizontal_rows": horizontal_rows,
            "vertical_cols": vertical_cols,
        })

    if deduplicate:
        candidates = _deduplicate_candidates(candidates)

    # Return the line mask in full-image coordinates for diagnostics.
    full_mask[
        offset_y:offset_y + image_height,
        offset_x:offset_x + image_width,
    ] = lines

    candidates.sort(
        key=lambda item: (
            _geometry_strength(item),
            item["box"][2] * item["box"][3],
        ),
        reverse=True,
    )

    return full_mask, candidates


def overlap_ratio(
    box,
    mask,
    padding: int = 5,
) -> float:
    """Return the fraction of a padded candidate region covered by mask."""
    x, y, width, height = map(int, box)

    if getattr(mask, "ndim", 0) != 2:
        raise ValueError("Mask must be a two-dimensional array.")

    if padding < 0:
        raise ValueError("Padding must be non-negative.")

    image_height, image_width = mask.shape

    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(image_width, x + width + padding)
    y2 = min(image_height, y + height + padding)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    roi = mask[y1:y2, x1:x2]

    if roi.size == 0:
        return 0.0

    return float(np.count_nonzero(roi) / roi.size)


def score_candidates(
    candidates: list[dict[str, Any]],
    selection_mask,
) -> list[dict[str, Any]]:
    """Rank frame candidates without inventing annotation associations.

    Selection overlap is supporting evidence only. If the selection
    mask does not overlap a candidate, the result explicitly states
    that the association has not been established.
    """
    if getattr(selection_mask, "ndim", 0) != 2:
        raise ValueError("Selection mask must be two-dimensional.")

    scored = []

    for candidate in candidates:
        overlap = overlap_ratio(
            candidate["box"],
            selection_mask,
            padding=4,
        )

        geometry = _geometry_strength(candidate)

        scored.append({
            **candidate,
            "selection_overlap": round(overlap, 5),
            "geometry_score": round(geometry, 4),
            "score": round(
                0.80 * geometry + 0.20 * min(overlap * 20, 1.0),
                4,
            ),
            "selection_association": (
                "overlap_supported"
                if overlap >= 0.005
                else "not_established"
            ),
        })

    scored.sort(
        key=lambda item: (
            item["selection_association"] == "overlap_supported",
            item["score"],
        ),
        reverse=True,
    )

    return scored


def locate_frame_candidates(
    rgb_image,
    selection_mask=None,
    roi: tuple[int, int, int, int] | None = None,
):
    """Detect and rank frames, optionally within a selected search region."""
    _, candidates = detect_frame_geometry(
        rgb_image,
        roi=roi,
    )

    if selection_mask is not None:
        if selection_mask.shape != rgb_image.shape[:2]:
            raise ValueError(
                "Selection mask dimensions must match the full RGB image."
            )

        return score_candidates(candidates, selection_mask)

    return sorted(
        candidates,
        key=lambda item: (
            _geometry_strength(item),
            item["box"][2] * item["box"][3],
        ),
        reverse=True,
    )


def save_crop(
    rgb_image,
    box,
    path: str | Path,
    margin_x: int = 10,
    margin_y: int = 8,
) -> None:
    """Save a padded RGB crop using OpenCV's BGR file convention."""
    _validate_rgb_image(rgb_image)

    if margin_x < 0 or margin_y < 0:
        raise ValueError("Crop margins must be non-negative.")

    x, y, width, height = map(int, box)
    image_height, image_width = rgb_image.shape[:2]

    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(image_width, x + width + margin_x)
    y2 = min(image_height, y + height + margin_y)

    crop = rgb_image[y1:y2, x1:x2]

    if crop.size == 0:
        raise ValueError(
            f"Candidate box {box!r} produced an empty crop."
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)

    if not cv2.imwrite(str(path), bgr):
        raise OSError(f"OpenCV could not write crop to {path}.")
