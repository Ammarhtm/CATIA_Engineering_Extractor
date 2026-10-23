
"""V6.1 — GD&T cell segmentation and cell-aware OCR.

Run:
    python -m pytest tests/integration/test_nonsemantic_ocr_v61.py -v -s

Reads V5 clean captures and V5.4 frame reports.
Does not modify CATIA.
"""

from itertools import combinations



from pathlib import Path
import json
import re

import cv2
import easyocr
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / "output" / "debug" / "nonsemantic_v5"
V54 = ROOT / "output" / "debug" / "nonsemantic_v54"
OUT = ROOT / "output" / "debug" / "nonsemantic_v61"

TARGETS = (
    "Geometrical Tolerance.1",
    "Geometrical Tolerance.2",
)

SCALE = 5


def safe_name(name):
    return name.replace(" ", "_").replace(".", "_")


@pytest.fixture(scope="module")
def reader():
    return easyocr.Reader(["en"], gpu=False)


def load_frame(name):
    safe = safe_name(name)

    image_path = V5 / f"{safe}_before.png"
    report_path = V54 / f"{safe}_report.json"

    assert image_path.is_file(), f"Missing image: {image_path}"
    assert report_path.is_file(), f"Missing report: {report_path}"

    image = cv2.imread(str(image_path))
    assert image is not None

    report = json.loads(report_path.read_text(encoding="utf-8"))
    box = report.get("frame")

    assert box is not None, f"No frame for {name}"

    x, y, w, h = map(int, box)
    ih, iw = image.shape[:2]

    assert w > 0 and h > 0
    assert 0 <= x and 0 <= y
    assert x + w <= iw and y + h <= ih

    return image[y:y+h, x:x+w].copy(), box


def neutral_mask(image):
    """White/gray strokes, excluding colored CAD geometry."""
    b, g, r = (
        image[:, :, i].astype(np.int16)
        for i in range(3)
    )

    low = np.minimum(np.minimum(b, g), r)
    high = np.maximum(np.maximum(b, g), r)

    return (
        ((low >= 125) & ((high - low) <= 65))
        .astype(np.uint8) * 255
    )


def vertical_support(mask):
    """Measure continuous vertical strokes across frame interior."""
    h, w = mask.shape

    if h < 8:
        return np.zeros(w, dtype=float)

    inner = mask[3:h-3, :]
    return np.mean(inner > 0, axis=0)


def group_positions(positions, max_gap=2):
    groups = []

    for x in positions:
        x = int(x)

        if groups and x - groups[-1][-1] <= max_gap:
            groups[-1].append(x)
        else:
            groups.append([x])

    return groups


def divider_score(mask, x):
    """Measure a vertical divider and its connection to frame borders."""
    h, w = mask.shape

    if not (3 <= x < w - 3):
        return 0.0

    # Check vertical continuity, allowing 1-pixel shifts.
    interior = mask[2:h - 2, x - 1:x + 2]
    vertical = float(np.mean(np.any(interior > 0, axis=1)))

    # Real cell dividers should meet both horizontal borders.
    top = mask[0:5, x - 2:x + 3]
    bottom = mask[h - 5:h, x - 2:x + 3]

    top_connected = float(np.any(top > 0))
    bottom_connected = float(np.any(bottom > 0))

    return (
        0.70 * vertical
        + 0.15 * top_connected
        + 0.15 * bottom_connected
    )


def detect_separators(frame):
    """Find two internal GD&T dividers using geometry constraints."""
    mask = neutral_mask(frame)
    h, w = mask.shape

    support = np.zeros(w, dtype=float)

    for x in range(w):
        support[x] = divider_score(mask, x)

    # Keep local maxima, excluding outer frame edges.
    candidates = []

    for x in range(6, w - 6):
        score = support[x]

        if score < 0.55:
            continue

        local = support[max(0, x - 3):min(w, x + 4)]

        if score >= np.max(local):
            if candidates and x - candidates[-1][0] <= 4:
                if score > candidates[-1][1]:
                    candidates[-1] = (x, score)
            else:
                candidates.append((x, score))

    best = None

    for (x1, s1), (x2, s2) in combinations(candidates, 2):
        if x1 >= x2:
            continue

        symbol_width = x1
        value_width = x2 - x1
        datum_width = w - x2

        # GD&T layout:
        # [symbol] [tolerance + modifiers] [datum]
        if not (0.45 * h <= symbol_width <= 1.8 * h):
            continue

        if value_width < 0.8 * h:
            continue

        if not (0.45 * h <= datum_width <= 1.8 * h):
            continue

        score = s1 + s2

        if best is None or score > best[0]:
            best = (score, x1, x2)

    if best is None:
        return [], support, mask

    return [best[1], best[2]], support, mask



def split_cells(frame, separators):
    """Split frame into individual cells."""
    h, w = frame.shape[:2]

    bounds = [0] + separators + [w]
    cells = []

    for index in range(len(bounds)-1):
        left = bounds[index]
        right = bounds[index+1]

        if right - left < 7:
            continue

        # Remove frame borders and dividers from OCR crop.
        x1 = min(right, left + 3)
        x2 = max(x1, right - 3)

        y1 = 3
        y2 = max(y1, h - 3)

        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            continue

        cells.append({
            "index": index,
            "bounds": [left, 0, right-left, h],
            "image": crop,
        })

    return cells


def preprocess_cell(image):
    enlarged = cv2.resize(
        image,
        None,
        fx=SCALE,
        fy=SCALE,
        interpolation=cv2.INTER_CUBIC,
    )

    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)

    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    return {
        "gray": gray,
        "binary": binary,
    }


def ocr_cell(reader, variants, allowlist):
    results = []

    for variant, image in variants.items():
        detections = reader.readtext(
            image,
            detail=1,
            paragraph=False,
            allowlist=allowlist,
            decoder="greedy",
            min_size=5,
            text_threshold=0.3,
            low_text=0.2,
            link_threshold=0.2,
        )

        for _, text, confidence in detections:
            results.append({
                "variant": variant,
                "text": str(text).strip(),
                "confidence": round(float(confidence), 4),
            })

    return results


def best_match(detections, pattern):
    matches = []

    for item in detections:
        text = item["text"].strip().upper().replace(",", ".")

        if re.fullmatch(pattern, text):
            matches.append({
                "text": text,
                "confidence": item["confidence"],
                "variant": item["variant"],
            })

    if not matches:
        return None

    return max(matches, key=lambda x: x["confidence"])


def analyze_cells(name, cells, reader):
    results = []

    for cell in cells:
        index = cell["index"]
        image = cell["image"]

        variants = preprocess_cell(image)

        # Numeric OCR is deliberately restricted to digits and decimals.
        numeric_detections = ocr_cell(
            reader,
            variants,
            "0123456789.,",
        )

        datum_detections = ocr_cell(
            reader,
            variants,
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        )

        numeric = best_match(
            numeric_detections,
            r"\d+(?:\.\d+)?",
        )

        datum = best_match(
            datum_detections,
            r"[A-Z]",
        )

        results.append({
            "index": index,
            "bounds": cell["bounds"],
            "numeric_candidate": numeric,
            "datum_candidate": datum,
            "numeric_ocr": numeric_detections,
            "datum_ocr": datum_detections,
            "status": "needs_validation",
        })

    return results


@pytest.mark.parametrize("name", TARGETS)
def test_nonsemantic_ocr_v61(name, reader):
    OUT.mkdir(parents=True, exist_ok=True)

    safe = safe_name(name)
    frame, box = load_frame(name)

    separators, support, mask = detect_separators(frame)
    cells = split_cells(frame, separators)

    debug = frame.copy()

    for x in separators:
        cv2.line(
            debug,
            (x, 0),
            (x, frame.shape[0]-1),
            (0, 255, 0),
            1,
        )

    cv2.imwrite(str(OUT / f"{safe}_segmentation.png"), debug)
    cv2.imwrite(str(OUT / f"{safe}_mask.png"), mask)

    for cell in cells:
        cv2.imwrite(
            str(OUT / f"{safe}_cell_{cell['index']}.png"),
            cell["image"],
        )

    cell_results = analyze_cells(name, cells, reader)

    report = {
        "annotation": name,
        "frame": box,
        "separators": separators,
        "cell_count": len(cells),
        "cells": cell_results,
        "status": "needs_validation",
    }

    output = OUT / f"{safe}_ocr_report.json"

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + json.dumps(
        report,
        indent=2,
        ensure_ascii=False,
    ))

    assert output.is_file()
    assert len(cells) >= 1
    assert len(separators) == 2, (
    f"{name}: expected 2 internal dividers, "
    f"detected {separators}. "
    "Segmentation needs review."
    )

    assert len(cells) == 3, (
        f"{name}: expected 3 cells, got {len(cells)}"
    )
