"""V5.2.1: tolerant GD&T frame detection from V5 clean screenshots.

Run: python -m pytest tests/integration/test_nonsemantic_frame_expansion_v521.py -v -s
No CATIA interaction. All detections require visual review.
"""
from pathlib import Path
import json

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / "output" / "debug" / "nonsemantic_v5"
OUT = ROOT / "output" / "debug" / "nonsemantic_v521"
TARGETS = ("Geometrical Tolerance.1", "Geometrical Tolerance.2")


def safe_name(name):
    return name.replace(" ", "_").replace(".", "_")


def runs_1d(bits):
    a = np.pad(np.asarray(bits, dtype=bool), (1, 1))
    d = np.diff(a.astype(np.int8))
    return list(zip(np.flatnonzero(d == 1).tolist(),
                    (np.flatnonzero(d == -1) - 1).tolist()))


def load_seed(name):
    report = V5 / "report.json"
    assert report.is_file(), f"Missing V5 report: {report}"
    item = json.loads(report.read_text(encoding="utf-8")).get(name, {})
    best = item.get("best") or {}
    assert "box" in best, f"No seed box for {name} in {report}"
    return tuple(map(int, best["box"]))


def white_strokes(image):
    """Prefer near-white strokes, excluding orange selection/view borders."""
    b, g, r = cv2.split(image)
    high = np.minimum(np.minimum(b, g), r) >= 135
    low = np.maximum(np.maximum(b, g), r)
    neutral = (low.astype(np.int16) - np.minimum(np.minimum(b, g), r).astype(np.int16)) <= 85
    return (high & neutral).astype(np.uint8) * 255


def recover_frame(image, seed):
    """Find a rectangular border near seed using tolerant row/column support.

    The seed may cover just the central cells. This returns a *candidate*, not
    a guaranteed semantic frame. All output must be visually reviewed.
    """
    x, y, sw, sh = map(int, seed)
    H, W = image.shape[:2]
    if min(sw, sh) <= 0 or x < 0 or y < 0 or x + sw > W or y + sh > H:
        return None, {"reason": "invalid seed"}

    mask = white_strokes(image)
    # Local search, scaled by seed size: excludes distant view boundary.
    pad_x = max(24, min(55, int(sw * 0.65)))
    pad_y = max(7, min(18, int(sh * 0.5)))
    x0, x1 = max(0, x - pad_x), min(W, x + sw + pad_x)
    y0, y1 = max(0, y - pad_y), min(H, y + sh + pad_y)
    roi = mask[y0:y1, x0:x1]

    # Bridge short gaps in the top/bottom line; never bridge large gaps to
    # unrelated geometry. Separately enhance vertical end caps.
    hmask = cv2.morphologyEx(roi, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)))
    vmask = cv2.morphologyEx(roi, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5)))

    def row_support(yy, left, right):
        if yy < 0 or yy >= roi.shape[0] or right <= left:
            return 0.0
        a = hmask[max(0, yy - 1):min(roi.shape[0], yy + 2), left:right + 1]
        return float(np.mean(np.any(a > 0, axis=0))) if a.size else 0.0

    def col_support(xx, top, bottom):
        if xx < 0 or xx >= roi.shape[1] or bottom <= top:
            return 0.0
        a = vmask[top:bottom + 1, max(0, xx - 1):min(roi.shape[1], xx + 2)]
        return float(np.mean(np.any(a > 0, axis=1))) if a.size else 0.0

    # Estimate top/bottom from rows crossing the seed's center area.
    mid_left = max(0, x - x0 + int(sw * 0.15))
    mid_right = min(roi.shape[1] - 1, x - x0 + int(sw * 0.85))
    row_strength = []
    for yy in range(roi.shape[0]):
        row_strength.append(row_support(yy, mid_left, mid_right))

    top_candidates = [i for i in range(max(0, y - y0 - 8), min(roi.shape[0], y - y0 + 9))
                      if row_strength[i] >= 0.48]
    bottom_target = y + sh - 1 - y0
    bottom_candidates = [i for i in range(max(0, bottom_target - 8),
                                          min(roi.shape[0], bottom_target + 9))
                         if row_strength[i] >= 0.48]

    diagnostics = {"top_rows": len(top_candidates), "bottom_rows": len(bottom_candidates),
                   "roi": [x0, y0, x1 - x0, y1 - y0]}
    if not top_candidates or not bottom_candidates:
        return None, {**diagnostics, "reason": "top or bottom stroke not found"}

    candidates = []
    sx0, sx1 = x - x0, x + sw - 1 - x0
    for top in top_candidates:
        for bottom in bottom_candidates:
            fh = bottom - top + 1
            if not (max(11, int(sh * 0.55)) <= fh <= sh + 14):
                continue
            # End caps must be outside/near the seed edges, not internal dividers.
            left_min = max(0, sx0 - pad_x)
            left_max = min(roi.shape[1] - 1, sx0 + 5)
            right_min = max(0, sx1 - 5)
            right_max = min(roi.shape[1] - 1, sx1 + pad_x)
            lefts = [(col_support(xx, top, bottom), xx)
                     for xx in range(left_min, left_max + 1)]
            rights = [(col_support(xx, top, bottom), xx)
                      for xx in range(right_min, right_max + 1)]
            lefts = [(s, xx) for s, xx in lefts if s >= 0.38]
            rights = [(s, xx) for s, xx in rights if s >= 0.38]
            for ls, left in lefts:
                for rs, right in rights:
                    if right - left < max(35, int(sw * 0.75)):
                        continue
                    ht = row_support(top, left, right)
                    hb = row_support(bottom, left, right)
                    if min(ht, hb) < 0.58:
                        continue
                    # Prefer boundaries just outside the seed; reject overexpansion.
                    excess = max(0, sx0 - left) + max(0, right - sx1)
                    asymmetry = abs((sx0 - left) - (right - sx1))
                    proximity = abs(top - (y - y0)) + abs(bottom - bottom_target)
                    score = (2.0 * min(ls, rs) + ht + hb
                             - 0.010 * excess - 0.012 * asymmetry
                             - 0.025 * proximity)
                    candidates.append((score, (x0 + left, y0 + top,
                                                right - left + 1, fh),
                                       {"left_support": round(ls, 3),
                                        "right_support": round(rs, 3),
                                        "top_support": round(ht, 3),
                                        "bottom_support": round(hb, 3)}))
    if not candidates:
        return None, {**diagnostics, "reason": "no border pair passed relaxed checks"}
    candidates.sort(key=lambda z: z[0], reverse=True)
    score, box, info = candidates[0]
    return box, {**diagnostics, **info, "score": round(float(score), 3),
                 "candidate_count": len(candidates)}


@pytest.mark.parametrize("name", TARGETS)
def test_nonsemantic_frame_expansion_v521(name):
    OUT.mkdir(parents=True, exist_ok=True)
    safe = safe_name(name)
    source = V5 / f"{safe}_before.png"
    assert source.is_file(), f"Missing clean screenshot: {source}"
    image = cv2.imread(str(source))
    assert image is not None, f"Cannot read: {source}"
    seed = load_seed(name)
    box, diagnostic = recover_frame(image, seed)

    debug = image.copy()
    sx, sy, sw, sh = seed
    cv2.rectangle(debug, (sx, sy), (sx + sw - 1, sy + sh - 1), (0, 255, 255), 1)
    if box is not None:
        bx, by, bw, bh = box
        cv2.rectangle(debug, (bx, by), (bx + bw - 1, by + bh - 1), (0, 255, 0), 2)
        margin = 4
        xa, ya = max(0, bx - margin), max(0, by - margin)
        xb, yb = min(image.shape[1], bx + bw + margin), min(image.shape[0], by + bh + margin)
        cv2.imwrite(str(OUT / f"{safe}_crop.png"), image[ya:yb, xa:xb])
    cv2.imwrite(str(OUT / f"{safe}_debug.png"), debug)
    report = {"annotation": name, "seed": seed, "frame": box,
              "diagnostic": diagnostic,
              "status": "candidate_needs_visual_review" if box else "needs_review"}
    (OUT / f"{safe}_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
    assert box is not None, f"Frame candidate not found: {diagnostic}"
