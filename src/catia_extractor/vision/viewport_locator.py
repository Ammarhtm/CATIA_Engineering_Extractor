
"""Automatic CATIA viewport localization.

Identifies a likely graphics viewport by detecting a persistent
vertical panel boundary in a CATIA window screenshot.

Returns a candidate region, not a guaranteed viewport identity.
If evidence is insufficient, the caller must review the result.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


VERSION = "1.0"


def _validate_image(image: Any) -> None:
    if (
        image is None
        or not isinstance(image, np.ndarray)
        or image.ndim != 3
        or image.shape[2] != 3
    ):
        raise ValueError(
            "Expected an RGB NumPy image with shape (height, width, 3)."
        )


def detect_viewport(
    rgb_image: np.ndarray,
    min_split_ratio: float = 0.12,
    max_split_ratio: float = 0.48,
    min_boundary_strength: float = 0.45,
) -> dict[str, Any]:
    """Estimate the graphics viewport to the right of the specification tree.

    The detector searches for a vertical boundary between the tree and
    the graphics area. The boundary must be supported by image evidence.

    Returns:
        {
            "version": ...,
            "status": "candidate" | "needs_review",
            "roi": (x, y, width, height) | None,
            "boundary_x": int | None,
            "boundary_strength": float,
            "reason": str,
        }

    Coordinates refer to the supplied image.
    """
    _validate_image(rgb_image)

    height, width = rgb_image.shape[:2]

    result = {
        "version": VERSION,
        "status": "needs_review",
        "roi": None,
        "boundary_x": None,
        "boundary_strength": 0.0,
        "reason": None,
    }

    if height < 100 or width < 200:
        result["reason"] = "image_too_small"
        return result

    gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)

    # Suppress isolated text strokes while preserving panel boundaries.
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    gradient_x = cv2.Sobel(
        blurred,
        cv2.CV_32F,
        1,
        0,
        ksize=3,
    )

    vertical_edges = np.abs(gradient_x)

    # Aggregate vertical-edge strength by column. A true panel divider
    # should usually extend through a substantial portion of the image.
    y1 = int(height * 0.08)
    y2 = int(height * 0.92)

    if y2 <= y1:
        result["reason"] = "invalid_search_region"
        return result

    column_strength = np.mean(
        vertical_edges[y1:y2, :],
        axis=0,
    )


    # Normalize using columns that contain actual edge evidence.
    # Sparse vertical separators must not disappear just because most
    # image columns contain no vertical edge.
    positive_strengths = column_strength[column_strength > 1e-6]

    if positive_strengths.size == 0:
        result["reason"] = "insufficient_vertical_edge_evidence"
        return result

    reference_strength = float(
        np.percentile(positive_strengths, 90)
    )

    if reference_strength <= 1e-6:
        result["reason"] = "insufficient_vertical_edge_evidence"
        return result

    normalized = np.clip(
        column_strength / reference_strength,
        0.0,
        1.0,
    )


    x_start = max(1, int(width * min_split_ratio))
    x_end = min(width - 1, int(width * max_split_ratio))

    if x_end <= x_start:
        result["reason"] = "invalid_boundary_search_range"
        return result

    # Smooth the column scores to reduce the effect of single-pixel edges.
    smooth = np.convolve(
        normalized,
        np.ones(5, dtype=np.float32) / 5.0,
        mode="same",
    )

    candidates = np.arange(x_start, x_end)
    best_x = int(candidates[np.argmax(smooth[candidates])])
    best_strength = float(smooth[best_x])

    result["boundary_x"] = best_x
    result["boundary_strength"] = round(best_strength, 4)

    if best_strength < min_boundary_strength:
        result["reason"] = "panel_boundary_not_confident"
        return result

    # Leave a small gap around the boundary to avoid including the
    # separator itself in the viewport.
    margin = max(2, int(width * 0.005))
    viewport_x = min(width - 1, best_x + margin)
    viewport_width = width - viewport_x

    if viewport_width < int(width * 0.35):
        result["reason"] = "candidate_viewport_too_narrow"
        return result

    result.update({
        "status": "candidate",
        "roi": (
            viewport_x,
            0,
            viewport_width,
            height,
        ),
        "reason": "vertical_panel_boundary_candidate",
    })

    return result


def draw_viewport_candidate(
    rgb_image: np.ndarray,
    detection: dict[str, Any],
) -> np.ndarray:
    """Create a diagnostic image showing the proposed viewport."""
    _validate_image(rgb_image)

    preview = cv2.cvtColor(
        rgb_image.copy(),
        cv2.COLOR_RGB2BGR,
    )

    roi = detection.get("roi")

    if roi is not None:
        x, y, width, height = map(int, roi)

        cv2.rectangle(
            preview,
            (x, y),
            (x + width - 1, y + height - 1),
            (0, 255, 0),
            2,
        )

    boundary_x = detection.get("boundary_x")

    if boundary_x is not None:
        cv2.line(
            preview,
            (int(boundary_x), 0),
            (int(boundary_x), preview.shape[0] - 1),
            (0, 0, 255),
            2,
        )

    return preview
