
"""V5.3: detect OUTER GD&T frame borders from a V5 clean capture.

Run: python -m pytest tests/integration/test_nonsemantic_frame_expansion_v53.py -v -s
Read-only image processing. Results are candidates requiring visual review.
"""
from pathlib import Path
import json
import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / 'output' / 'debug' / 'nonsemantic_v5'
OUT = ROOT / 'output' / 'debug' / 'nonsemantic_v53'
TARGETS = ('Geometrical Tolerance.1', 'Geometrical Tolerance.2')


def safe_name(name):
    return name.replace(' ', '_').replace('.', '_')


def load_seed(name):
    path = V5 / 'report.json'
    assert path.is_file(), f'Missing {path}'
    item = json.loads(path.read_text(encoding='utf-8')).get(name, {})
    best = item.get('best') or {}
    assert 'box' in best, f'Missing seed for {name}'
    return tuple(map(int, best['box']))


def neutral_strokes(image):
    b, g, r = (image[:, :, i].astype(np.int16) for i in range(3))
    lo = np.minimum(np.minimum(b, g), r)
    hi = np.maximum(np.maximum(b, g), r)
    # Exclude orange view outlines and green selection markers.
    return ((lo >= 140) & ((hi - lo) <= 55)).astype(np.uint8) * 255


def segments(bits):
    a = np.pad(np.asarray(bits, dtype=bool), (1, 1))
    d = np.diff(a.astype(np.int8))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def recover_frame(image, seed):
    x, y, sw, sh = map(int, seed)
    H, W = image.shape[:2]
    if sw <= 0 or sh <= 0 or x < 0 or y < 0 or x + sw > W or y + sh > H:
        return None, {'reason': 'invalid seed'}

    # Keep the search local, relative to seed dimensions, never screen coordinates.
    padx = max(38, min(100, round(sw * 0.85)))
    pady = max(9, min(18, round(sh * 0.4)))
    x0, x1 = max(0, x - padx), min(W, x + sw + padx)
    y0, y1 = max(0, y - pady), min(H, y + sh + pady)
    roi = neutral_strokes(image[y0:y1, x0:x1])
    rh, rw = roi.shape
    sx0, sx1 = x - x0, x + sw - 1 - x0
    sy0, sy1 = y - y0, y + sh - 1 - y0

    # Only connect small interruptions on a *single horizontal line*.
    horizontal = cv2.morphologyEx(
        roi, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)))
    vertical = cv2.morphologyEx(
        roi, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))

    def row_coverage(yy, left, right):
        if not (0 <= yy < rh) or right <= left:
            return 0.0
        slab = horizontal[max(0, yy - 1):min(rh, yy + 2), left:right + 1]
        return float(np.mean(np.any(slab != 0, axis=0)))

    def cap_support(xx, top, bottom):
        if not (0 <= xx < rw) or bottom <= top:
            return 0.0
        slab = vertical[top:bottom + 1, max(0, xx - 1):min(rw, xx + 2)]
        return float(np.mean(np.any(slab != 0, axis=1)))

    def row_candidates(target):
        found = []
        for yy in range(max(0, target - 8), min(rh, target + 9)):
            # Need a horizontal border crossing the middle of the seed.
            runs = segments(horizontal[yy] != 0)
            for l, r in runs:
                if r - l + 1 < max(18, int(sw * 0.32)):
                    continue
                if l <= (sx0 + sx1) // 2 <= r:
                    found.append((yy, int(l), int(r)))
        return found

    tops = row_candidates(sy0)
    bottoms = row_candidates(sy1)
    candidates = []
    for top, tl, tr in tops:
        for bottom, bl, br in bottoms:
            fh = bottom - top + 1
            if not (max(12, int(sh * 0.55)) <= fh <= sh + 14):
                continue
            # Use the common run as evidence of top/bottom frame lines.
            common_l, common_r = max(tl, bl), min(tr, br)
            if common_r - common_l < max(20, int(sw * 0.35)):
                continue

            # Search *outside* the seed's value cell, not inside it.
            # Both outer end caps must be supported by the same top/bottom borders.
            left_options = range(max(0, sx0 - padx), min(rw, sx0 + 3))
            right_options = range(max(0, sx1 - 2), min(rw, sx1 + padx + 1))
            left_caps = [(xx, cap_support(xx, top, bottom)) for xx in left_options]
            right_caps = [(xx, cap_support(xx, top, bottom)) for xx in right_options]
            left_caps = [(xx, s) for xx, s in left_caps if s >= 0.52]
            right_caps = [(xx, s) for xx, s in right_caps if s >= 0.52]

            for left, ls in left_caps:
                for right, rs in right_caps:
                    if right - left < max(sw + 8, int(sw * 1.12)):
                        continue  # Crucial: reject central value-only cells.
                    if not (left <= sx0 + 2 and right >= sx1 - 2):
                        continue
                    ht, hb = row_coverage(top, left, right), row_coverage(bottom, left, right)
                    if min(ht, hb) < 0.70:
                        continue
                    # Outer caps should coincide with BOTH horizontal borders.
                    end_ok = all(row_coverage(yy, max(0, xx - 3), min(rw - 1, xx + 3)) >= 0.35
                                 for yy in (top, bottom) for xx in (left, right))
                    if not end_ok:
                        continue
                    # Penalize overexpansion; prefer widest *valid* connected frame,
                    # not merely the farthest right-hand line.
                    extra = (sx0 - left) + (right - sx1)
                    proximity = abs(top - sy0) + abs(bottom - sy1)
                    score = (2 * min(ls, rs) + ht + hb + 0.003 * (right - left)
                             - 0.010 * extra - 0.025 * proximity)
                    candidates.append((score, (x0 + left, y0 + top, right - left + 1, fh),
                                       {'top': y0 + top, 'bottom': y0 + bottom,
                                        'left_cap': round(ls, 3), 'right_cap': round(rs, 3),
                                        'top_line': round(ht, 3), 'bottom_line': round(hb, 3)}))

    diagnostics = {'roi': [x0, y0, x1 - x0, y1 - y0],
                   'top_runs': len(tops), 'bottom_runs': len(bottoms),
                   'candidate_count': len(candidates)}
    if not candidates:
        return None, {**diagnostics, 'reason': 'no complete outer frame met line/cap checks'}
    candidates.sort(key=lambda item: item[0], reverse=True)
    score, box, info = candidates[0]
    return box, {**diagnostics, **info, 'score': round(float(score), 3)}


@pytest.mark.parametrize('name', TARGETS)
def test_nonsemantic_frame_expansion_v53(name):
    OUT.mkdir(parents=True, exist_ok=True)
    safe = safe_name(name)
    source = V5 / f'{safe}_before.png'
    assert source.is_file(), f'Missing clean screenshot: {source}'
    image = cv2.imread(str(source))
    assert image is not None, f'Cannot read: {source}'
    seed = load_seed(name)
    box, info = recover_frame(image, seed)

    debug = image.copy()
    sx, sy, sw, sh = seed
    cv2.rectangle(debug, (sx, sy), (sx + sw - 1, sy + sh - 1), (0, 255, 255), 1)
    if box is not None:
        bx, by, bw, bh = box
        cv2.rectangle(debug, (bx, by), (bx + bw - 1, by + bh - 1), (0, 255, 0), 2)
        margin = 4
        xa, ya = max(0, bx - margin), max(0, by - margin)
        xb, yb = min(image.shape[1], bx + bw + margin), min(image.shape[0], by + bh + margin)
        cv2.imwrite(str(OUT / f'{safe}_crop.png'), image[ya:yb, xa:xb])
    cv2.imwrite(str(OUT / f'{safe}_debug.png'), debug)
    report = {'annotation': name, 'seed': seed, 'frame': box,
              'diagnostic': info, 'status': 'candidate_needs_visual_review' if box else 'needs_review'}
    (OUT / f'{safe}_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('\n' + json.dumps(report, indent=2))
    assert box is not None, f'No outer frame candidate: {info}'
