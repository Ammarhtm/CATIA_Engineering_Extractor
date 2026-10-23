
"""V6.2 — Geometry-aware GD&T segmentation and cell-aware OCR.

Run:
    python -m pytest tests/integration/test_nonsemantic_ocr_v62.py -v -s

Reads V5 clean captures and V5.4 frame reports.
Does not modify CATIA.
OCR results remain provisional until visually validated.
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
OUT = ROOT / "output" / "debug" / "nonsemantic_v62"

TARGETS = (
    "Geometrical Tolerance.1",
    "Geometrical Tolerance.2",
)

SCALE = 5
MIN_DIVIDER_SCORE = 0.48


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
    assert report_path.is_file(), f"Missing V5.4 report: {report_path}"

    image = cv2.imread(str(image_path))
    assert image is not None, f"Cannot read image: {image_path}"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    box = report.get("frame")

    assert box is not None, (
        f"No verified frame candidate for {name}; "
        "review the V5.4 frame report first."
    )

    x, y, w, h = map(int, box)
    ih, iw = image.shape[:2]

    assert w > 0 and h > 0
    assert x >= 0 and y >= 0
    assert x + w <= iw and y + h <= ih

    return image[y:y + h, x:x + w].copy(), box


def neutral_mask(image):
    """Keep neutral white/gray CAD strokes, excluding colored geometry."""
    b, g, r = (
        image[:, :, i].astype(np.int16)
        for i in range(3)
    )

    low = np.minimum(np.minimum(b, g), r)
    high = np.maximum(np.maximum(b, g), r)

    selected = (low >= 115) & ((high - low) <= 75)
    return selected.astype(np.uint8) * 255


def detect_separators(frame):
    """Find two internal dividers using stroke continuity and cell geometry.

    Expected layout:
        [geometric symbol] [value / modifiers] [datum]

    Returns:
        separators, diagnostic, neutral_mask
    """
    mask = neutral_mask(frame)
    h, w = mask.shape

    if h < 12 or w < 30:
        return [], {"reason": "frame too small", "candidates": []}, mask

    # Remove isolated short marks while preserving long vertical strokes.
    kernel_height = max(5, min(11, h // 3))
    vertical_lines = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(
            cv2.MORPH_RECT, (1, kernel_height)
        ),
    )

    y1 = 2
    y2 = h - 2

    raw_scores = np.zeros(w, dtype=float)
    line_scores = np.zeros(w, dtype=float)

    for x in range(3, w - 3):
        slab = mask[y1:y2, x - 1:x + 2]
        line_slab = vertical_lines[y1:y2, x - 1:x + 2]

        raw_scores[x] = (
            float(np.mean(np.any(slab > 0, axis=1)))
            if slab.size else 0.0
        )
        line_scores[x] = (
            float(np.mean(np.any(line_slab > 0, axis=1)))
            if line_slab.size else 0.0
        )

    # Blend raw continuity with morphological line evidence.
    scores = 0.55 * raw_scores + 0.45 * line_scores

    # Group neighboring strong columns into one divider candidate.
    strong = [
        x for x in range(4, w - 4)
        if scores[x] >= MIN_DIVIDER_SCORE
    ]

    groups = []
    for x in strong:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])

    candidates = []
    for group in groups:
        representative = max(group, key=lambda p: scores[p])
        candidates.append({
            "x": int(representative),
            "score": round(float(scores[representative]), 4),
        })

    if len(candidates) < 2:
        return [], {
            "reason": "fewer than two divider candidates",
            "candidates": candidates,
        }, mask

    # Frame proportions are deliberately broad because symbol-cell
    # widths differ between geometric tolerance types.
    min_symbol = max(7, int(0.35 * h))
    max_symbol = int(1.65 * h)
    min_value = max(10, int(0.80 * h))
    min_datum = max(7, int(0.45 * h))
    max_datum = int(1.70 * h)

    pair_options = []

    for first, second in combinations(candidates, 2):
        x1 = first["x"]
        x2 = second["x"]

        symbol_width = x1
        value_width = x2 - x1
        datum_width = w - x2

        if not (min_symbol <= symbol_width <= max_symbol):
            continue
        if value_width < min_value:
            continue
        if not (min_datum <= datum_width <= max_datum):
            continue

        # Prefer complete divider strokes and plausible cell proportions.
        symbol_ratio = symbol_width / max(h, 1)
        datum_ratio = datum_width / max(h, 1)

        geometry_penalty = (
            0.16 * abs(symbol_ratio - 0.80)
            + 0.12 * abs(datum_ratio - 0.80)
        )

        score = (
            first["score"]
            + second["score"]
            - geometry_penalty
        )

        pair_options.append({
            "score": float(score),
            "separators": [x1, x2],
            "cell_widths": [
                symbol_width, value_width, datum_width
            ],
            "divider_scores": [
                first["score"], second["score"]
            ],
        })

    if not pair_options:
        return [], {
            "reason": "no divider pair satisfies cell geometry",
            "candidates": candidates,
            "frame_size": [w, h],
            "constraints": {
                "min_symbol_width": min_symbol,
                "min_value_width": min_value,
                "min_datum_width": min_datum,
            },
        }, mask

    pair_options.sort(key=lambda item: item["score"], reverse=True)
    best = pair_options[0]

    diagnostic = {
        "candidates": candidates,
        "selected_pair": best,
        "alternative_pair_count": len(pair_options) - 1,
        "method": "vertical continuity + cell proportions",
        "status": "provisional_needs_visual_review",
    }

    return best["separators"], diagnostic, mask


def split_cells(frame, separators):
    """Create three crops while preserving glyph strokes."""
    h, w = frame.shape[:2]

    bounds = [0] + list(separators) + [w]
    cells = []

    roles = ("symbol", "value_and_modifiers", "datum")

    for index, (left, right) in enumerate(
        zip(bounds[:-1], bounds[1:])
    ):
        if right - left < 7:
            continue

        # Exclude outer frame strokes and divider lines.
        x1 = min(right, left + 2)
        x2 = max(x1, right - 2)
        y1 = min(h, 2)
        y2 = max(y1, h - 2)

        crop = frame[y1:y2, x1:x2].copy()

        if crop.size == 0:
            continue

        cells.append({
            "index": index,
            "role": roles[index] if index < len(roles) else "unknown",
            "bounds": [x1, y1, x2 - x1, y2 - y1],
            "image": crop,
        })

    return cells


def preprocess_cell(image):
    """Create independent OCR variants without changing the source crop."""
    enlarged = cv2.resize(
        image,
        None,
        fx=SCALE,
        fy=SCALE,
        interpolation=cv2.INTER_CUBIC,
    )

    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)

    # Add a white border so OCR does not clip characters at the edges.
    gray = cv2.copyMakeBorder(
        gray, 12, 12, 12, 12,
        cv2.BORDER_CONSTANT,
        value=255,
    )

    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    return {
        "gray": gray,
        "binary": binary,
        "inverted": cv2.bitwise_not(binary),
    }


def ocr_cell(reader, variants, allowlist=None):
    """Return raw detections with their source variant."""
    results = []

    for variant, image in variants.items():
        kwargs = {
            "detail": 1,
            "paragraph": False,
            "decoder": "greedy",
            "min_size": 5,
            "text_threshold": 0.30,
            "low_text": 0.20,
            "link_threshold": 0.20,
        }

        if allowlist:
            kwargs["allowlist"] = allowlist

        detections = reader.readtext(image, **kwargs)

        for polygon, text, confidence in detections:
            results.append({
                "variant": variant,
                "text": str(text).strip(),
                "confidence": round(float(confidence), 4),
                "bbox": [
                    [round(float(point[0]), 1),
                     round(float(point[1]), 1)]
                    for point in polygon
                ],
            })

    return results


def numeric_candidates(detections):
    """Extract numeric tokens without silently inventing missing decimals."""
    results = []

    for item in detections:
        raw = item["text"].strip().replace(",", ".")

        # Do not turn OCR text such as "L.055" into a trusted value.
        tokens = re.findall(
            r"(?<![A-Z0-9])(?:\d+(?:\.\d+)?|\.\d+)(?![A-Z0-9])",
            raw.upper(),
        )

        for token in tokens:
            normalized = token
            if normalized.startswith("."):
                normalized = "0" + normalized

            try:
                value = float(normalized)
            except ValueError:
                continue

            results.append({
                "value": value,
                "raw": raw,
                "token": normalized,
                "confidence": item["confidence"],
                "variant": item["variant"],
            })

    return results


def best_numeric(detections):
    candidates = numeric_candidates(detections)

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: item["confidence"],
    )


def best_datum(detections):
    candidates = []

    for item in detections:
        text = re.sub(r"[^A-Z]", "", item["text"].upper())

        if len(text) == 1:
            candidates.append({
                "value": text,
                "raw": item["text"],
                "confidence": item["confidence"],
                "variant": item["variant"],
            })

    if not candidates:
        return None

    return max(candidates, key=lambda item: item["confidence"])


def analyze_cells(cells, reader):
    results = []

    for cell in cells:
        variants = preprocess_cell(cell["image"])
        role = cell["role"]

        result = {
            "index": cell["index"],
            "role": role,
            "bounds": cell["bounds"],
            "numeric_candidate": None,
            "datum_candidate": None,
            "raw_ocr": [],
            "status": "needs_validation",
        }

        # Symbols are not reliable as ordinary alphanumeric OCR.
        # Preserve their image crop for later symbol-specific recognition.
        if role == "symbol":
            result["symbol_recognition"] = {
                "status": "not_attempted",
                "note": "Requires a dedicated geometric-symbol classifier.",
            }
            results.append(result)
            continue

        if role == "value_and_modifiers":
            numeric_raw = ocr_cell(
                reader,
                variants,
                allowlist="0123456789.,",
            )

            # Keep a separate unrestricted pass for diagnostic purposes.
            general_raw = ocr_cell(reader, variants)

            result["numeric_ocr"] = numeric_raw
            result["general_ocr"] = general_raw
            result["numeric_candidate"] = best_numeric(numeric_raw)

            result["raw_ocr"] = general_raw

        elif role == "datum":
            datum_raw = ocr_cell(
                reader,
                variants,
                allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            )

            result["datum_ocr"] = datum_raw
            result["datum_candidate"] = best_datum(datum_raw)
            result["raw_ocr"] = datum_raw

        results.append(result)

    return results


@pytest.mark.parametrize("name", TARGETS)
def test_nonsemantic_ocr_v62(name, reader):
    OUT.mkdir(parents=True, exist_ok=True)

    safe = safe_name(name)
    frame, frame_box = load_frame(name)

    separators, segmentation_info, mask = detect_separators(frame)
    cells = split_cells(frame, separators)

    debug = frame.copy()

    for x in separators:
        cv2.line(
            debug,
            (x, 0),
            (x, frame.shape[0] - 1),
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

    cell_results = analyze_cells(cells, reader)

    value_cell = next(
        (item for item in cell_results
         if item["role"] == "value_and_modifiers"),
        None,
    )
    datum_cell = next(
        (item for item in cell_results if item["role"] == "datum"),
        None,
    )

    report = {
        "version": "6.2",
        "annotation": name,
        "frame": frame_box,
        "frame_size": [
            int(frame.shape[1]), int(frame.shape[0])
        ],
        "separators": separators,
        "segmentation_diagnostic": segmentation_info,
        "cell_count": len(cells),
        "cells": cell_results,
        "summary": {
            "numeric_candidate": (
                value_cell["numeric_candidate"] if value_cell else None
            ),
            "datum_candidate": (
                datum_cell["datum_candidate"] if datum_cell else None
            ),
            "symbol_classification": "not_implemented",
        },
        "status": "needs_validation",
    }

    output = OUT / f"{safe}_ocr_report.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + json.dumps(
        report, indent=2, ensure_ascii=False
    ))

    # These assertions validate segmentation, not OCR correctness.
    assert len(separators) == 2, (
        f"{name}: expected 2 internal dividers; got {separators}. "
        f"Diagnostic: {segmentation_info}"
    )

    assert len(cells) == 3, (
        f"{name}: expected 3 cells; got {len(cells)}"
    )

    assert output.is_file()
