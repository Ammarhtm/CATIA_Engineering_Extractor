
"""GD&T full-frame locator v2.3 (adaptive contrast).

Expands a seed candidate to an axis-aligned feature-control frame.
Uses image geometry without hardcoded annotation names or coordinates.
Results are provisional and still require engineering review.

Call signature and JSON output are compatible with Pipeline 2 runner.
"""

from __future__ import annotations

import cv2
import numpy as np


def _failed(seed, reason):
    return {
        "status": "full_frame_not_established",
        "seed_box": list(seed),
        "box": None,
        "border_evidence": None,
        "reason": reason,
        "engineering_approval": False,
    }


def _light_lines(rgb):
    """Extract pale CAD strokes despite CATIA background gradients.

    The previous fixed brightness threshold (V >= 125) mistakenly marked
    bright parts of CATIA's blue/gray background as *solid white pixels*.
    In the lower-right portion of some captures, that hides true FCF
    borders altogether.

    A median-filtered background estimate is subtracted locally.  Thin
    light CAD strokes stand out from the smooth background, irrespective
    of the screen position.  Saturation and minimum-channel checks still
    exclude saturated magenta solids / colored selection highlights.

    No hardcoded annotation names, screen coordinates or frame values.
    """
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # 31x31 is larger than a CAD outline but smaller than most text cells.
    # Median keeps smooth CATIA gradients while removing thin CAD strokes.
    local_background = cv2.medianBlur(gray, 31)
    contrast = (
        gray.astype(np.int16)
        - local_background.astype(np.int16)
    )

    # Anti-aliased white/gray CAD strokes are locally brighter than the
    # background.  Gray components and HSV saturation suppress colored
    # geometry / highlighted selections.
    pale_stroke = (
        (contrast >= 28)
        & (hsv[:, :, 1] <= 145)
        & (np.min(rgb, axis=2) > 110)
    )

    return (pale_stroke.astype(np.uint8) * 255)

def _runs(row):
    """Return start/end positions of bright runs."""
    values = np.r_[
        0,
        np.uint8(row > 0),
        0,
    ]

    diff = np.diff(
        values.astype(np.int16)
    )

    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1)

    return list(
        zip(
            starts.tolist(),
            ends.tolist(),
        )
    )


def _line_options(
    binary,
    expected_y,
    sx,
    sw,
    sh,
    max_width,
):
    """Look for horizontal frame edges near a seed."""
    height, width = binary.shape

    radius = max(
        4,
        round(sh * 0.18),
    )

    options = []

    for y in range(
        max(0, expected_y - radius),
        min(
            height,
            expected_y + radius + 1,
        ),
    ):
        y0 = max(0, y - 2)
        y1 = min(height, y + 3)

        profile = np.uint8(
            np.any(
                binary[y0:y1] > 0,
                axis=0,
            )
        ) * 255

        kernel_width = max(
            5,
            round(sh * 0.25),
        )

        profile = cv2.morphologyEx(
            profile[None, :],
            cv2.MORPH_CLOSE,
            np.ones(
                (1, kernel_width),
                np.uint8,
            ),
        )[0]

        for left, right in _runs(profile):
            run_width = right - left

            overlap = max(
                0,
                min(right, sx + sw)
                - max(left, sx),
            )

            if overlap < 0.55 * sw:
                continue

            if run_width < 0.8 * sw:
                continue

            if run_width > max_width:
                continue

            options.append(
                (
                    left,
                    right,
                    y,
                    overlap / sw,
                )
            )

    options.sort(
        key=lambda item: (
            -item[3],
            abs(item[2] - expected_y),
            -(item[1] - item[0]),
        )
    )

    return options[:40]


def _vertical(
    binary,
    x,
    top,
    bottom,
    band=2,
):
    """Measure coverage of a vertical line."""
    width = binary.shape[1]

    strip = binary[
        top:bottom + 1,
        max(0, x - band):
        min(width, x + band + 1),
    ]

    if not strip.size:
        return 0.0

    return float(
        np.mean(
            np.any(strip > 0, axis=1)
        )
    )


def _horizontal(
    binary,
    y,
    left,
    right,
):
    """Measure coverage of a horizontal border."""
    strip = binary[
        max(0, y - 2):
        min(binary.shape[0], y + 3),
        left:right,
    ]

    if not strip.size:
        return 0.0

    return float(
        np.mean(
            np.any(strip > 0, axis=0)
        )
    )


def _dividers(
    binary,
    left,
    right,
    top,
    bottom,
    seed_height,
):
    """Find vertical cell separator lines."""
    hits = []

    for x in range(left, right):
        coverage = _vertical(
            binary,
            x,
            top,
            bottom,
            band=1,
        )

        if coverage >= 0.52:
            hits.append((x, coverage))

    groups = []

    for x, coverage in hits:
        gap_limit = max(
            2,
            round(seed_height * 0.07),
        )

        if (
            not groups
            or x - groups[-1][-1][0]
            > gap_limit
        ):
            groups.append([])

        groups[-1].append(
            (x, coverage)
        )

    return [
        max(
            group,
            key=lambda item: item[1],
        )[0]
        for group in groups
    ]


def expand_to_full_frame(
    before_rgb,
    seed_candidate,
):
    """Expand an associated cell into a possible full FCF.

    Parameters:
        before_rgb:
            Clean RGB screenshot.

        seed_candidate:
            Dictionary containing a box:
            [x, y, width, height].

    Returns:
        A provisional full-frame candidate or a
        structured failure reason.
    """
    seed = tuple(
        map(
            int,
            seed_candidate["box"],
        )
    )

    sx, sy, sw, sh = seed

    if (
        before_rgb is None
        or before_rgb.ndim != 3
        or before_rgb.shape[2] != 3
    ):
        raise ValueError(
            "before_rgb must be an RGB image."
        )

    image_h, image_w = (
        before_rgb.shape[:2]
    )

    if (
        sw < 5
        or sh < 5
        or sx < 0
        or sy < 0
        or sx + sw > image_w
        or sy + sh > image_h
    ):
        return _failed(
            seed,
            "Seed outside image or too small.",
        )

    binary = _light_lines(
        before_rgb
    )

    max_width = min(
        image_w,
        max(
            sw * 7,
            round(sh * 12),
        ),
    )

    # Detect top and bottom near the selected cell.
    tops = _line_options(
        binary,
        sy,
        sx,
        sw,
        sh,
        max_width,
    )

    bottoms = _line_options(
        binary,
        sy + sh - 1,
        sx,
        sw,
        sh,
        max_width,
    )

    if not tops or not bottoms:
        return _failed(
            seed,
            "No plausible top/bottom lines near seed.",
        )

    solutions = []

    for top in tops:
        for bottom in bottoms:
            tx1, tx2, ty, _ = top
            bx1, bx2, by, _ = bottom

            frame_height = (
                by - ty + 1
            )

            if not (
                0.75 * sh
                <= frame_height
                <= 1.4 * sh
            ):
                continue

            left = min(
                tx1,
                bx1,
            )

            right = max(
                tx2,
                bx2,
            )

            frame_width = (
                right - left
            )

            if frame_width < sw * 1.15:
                continue

            if frame_width > max_width:
                continue

            tolerance = max(
                9,
                0.4 * sh,
            )

            if abs(tx1 - bx1) > tolerance:
                continue

            if abs(tx2 - bx2) > tolerance:
                continue

            if left > sx + max(
                3,
                0.15 * sw,
            ):
                continue

            if right < sx + sw - max(
                3,
                0.15 * sw,
            ):
                continue

            # Outer border evidence.
            top_coverage = _horizontal(
                binary,
                ty,
                left,
                right,
            )

            bottom_coverage = _horizontal(
                binary,
                by,
                left,
                right,
            )

            left_wall = _vertical(
                binary,
                left,
                ty,
                by,
            )

            right_wall = _vertical(
                binary,
                right - 1,
                ty,
                by,
            )

            if min(
                top_coverage,
                bottom_coverage,
            ) < 0.62:
                continue

            if min(
                left_wall,
                right_wall,
            ) < 0.40:
                continue

            # Verify internal cell boundaries.
            dividers = _dividers(
                binary,
                left,
                right,
                ty,
                by,
                sh,
            )

            margin = max(
                3,
                0.1 * sh,
            )

            internal = [
                x
                for x in dividers
                if left + margin
                < x
                < right - margin
            ]

            if not internal:
                continue

            score = (
                0.28 * top_coverage
                + 0.28 * bottom_coverage
                + 0.17 * left_wall
                + 0.17 * right_wall
                + 0.10
                * min(len(internal), 2)
                / 2
            )

            box = [
                int(left),
                int(ty),
                int(frame_width),
                int(frame_height),
            ]

            evidence = {
                "top_border": round(
                    top_coverage,
                    4,
                ),
                "bottom_border": round(
                    bottom_coverage,
                    4,
                ),
                "left_wall": round(
                    left_wall,
                    4,
                ),
                "right_wall": round(
                    right_wall,
                    4,
                ),
                "internal_dividers_x": internal,
                "score": round(
                    score,
                    4,
                ),
            }

            solutions.append(
                (
                    score,
                    box,
                    evidence,
                )
            )

    if not solutions:
        return _failed(
            seed,
            "No complete multi-cell outer border "
            "verified near seed.",
        )

    solutions.sort(
        key=lambda item: (
            item[0],
            item[1][2],
        ),
        reverse=True,
    )

    _, best_box, evidence = (
        solutions[0]
    )

    # A 5-row measurement band is used to score outer lines.  Its best
    # center may sit 1-2 pixels INSIDE the true anti-aliased border.
    # Include a small safety margin so image crops keep every stroke.
    # Padding is an image-scale tolerance, never a hardcoded screen box.
    x, y, w, h = best_box
    padding = 2
    left = max(0, x - padding)
    top = max(0, y - padding)
    right = min(image_w, x + w + padding)
    bottom = min(image_h, y + h + padding)
    best_box = [left, top, right - left, bottom - top]
    evidence["crop_padding_px"] = padding

    return {
        "status": "full_frame_candidate_needs_review",
        "seed_box": list(seed),
        "box": best_box,
        "border_evidence": evidence,
        "reason": (
            "Outer borders and at least one "
            "internal divider detected."
        ),
        "engineering_approval": False,
    }
