
"""Selection-guided detection of CATIA GD&T frame candidates.

Combines existing before/after capture analysis with the existing
OpenCV frame locator. It does not rerun OCR or modify the CATIA model.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from catia_extractor.vision.capture import selection_change_mask
from catia_extractor.vision.frame_locator import locate_frame_candidates


VERSION = "1.0"


def locate_selected_annotation_frame(
    before_rgb: np.ndarray,
    after_rgb: np.ndarray,
    roi: tuple[int, int, int, int] | None = None,
    min_selection_pixels: int = 3,
) -> dict[str, Any]:
    """Rank frame candidates using visual changes caused by selection.

    Args:
        before_rgb: RGB screenshot before selecting the annotation.
        after_rgb: RGB screenshot after selecting the annotation.
        roi: Optional search region in full-image coordinates.
        min_selection_pixels: Minimum orange changed pixels required
            before selection evidence is considered usable.

    Returns:
        A diagnostic report containing ranked candidates and status.
        No candidate is treated as an engineering-approved result.
    """
    if (
        before_rgb is None
        or after_rgb is None
        or not isinstance(before_rgb, np.ndarray)
        or not isinstance(after_rgb, np.ndarray)
    ):
        raise ValueError("Before and after must be NumPy RGB images.")

    if (
        before_rgb.ndim != 3
        or after_rgb.ndim != 3
        or before_rgb.shape[2] != 3
        or after_rgb.shape[2] != 3
    ):
        raise ValueError("Both images must have shape (height, width, 3).")

    if before_rgb.shape != after_rgb.shape:
        raise ValueError("Before and after images must have identical shapes.")

    if min_selection_pixels < 1:
        raise ValueError("min_selection_pixels must be at least 1.")

    selection_mask = selection_change_mask(
        before_rgb,
        after_rgb,
    )

    selected_pixel_count = int(
        np.count_nonzero(selection_mask)
    )

    base_report = {
        "version": VERSION,
        "selected_pixel_count": selected_pixel_count,
        "selection_evidence_available": (
            selected_pixel_count >= min_selection_pixels
        ),
        "roi": roi,
        "candidates": [],
        "status": None,
        "engineering_approval": False,
    }

    if selected_pixel_count < min_selection_pixels:
        base_report.update({
            "status": "no_reliable_selection_change",
            "note": (
                "No sufficient orange changed-pixel evidence was found. "
                "Check the selection and capture before associating a frame."
            ),
        })
        return base_report

    candidates = locate_frame_candidates(
        after_rgb,
        selection_mask=selection_mask,
        roi=roi,
    )

    base_report["candidates"] = candidates

    if not candidates:
        base_report.update({
            "status": "no_frame_candidates",
            "note": (
                "Selection evidence exists, but no plausible frame "
                "was detected in the requested search region."
            ),
        })
        return base_report

    supported = [
        candidate
        for candidate in candidates
        if candidate.get("selection_association")
        == "overlap_supported"
    ]

    if supported:
        status = "selection_overlap_candidates_found"
        note = (
            "One or more frame candidates overlap the selection-change "
            "mask. This is supporting evidence, not proof of identity."
        )
    else:
        status = "candidates_without_selection_overlap"
        note = (
            "Frames were detected, but none has sufficient overlap with "
            "the selection-change mask to support an association."
        )

    base_report.update({
        "status": status,
        "selection_overlap_candidate_count": len(supported),
        "note": note,
    })

    return base_report
