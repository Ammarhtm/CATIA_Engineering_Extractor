"""V5.4: extend V5.3 GD&T candidates LEFT to include the symbol cell.

Run: python -m pytest tests/integration/test_nonsemantic_frame_expansion_v54.py -v -s
Uses V5 clean screenshots and seed report; does not modify CATIA.
Candidate boxes always require visual review.
"""
from pathlib import Path
import json
import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / 'output' / 'debug' / 'nonsemantic_v5'
OUT = ROOT / 'output' / 'debug' / 'nonsemantic_v54'
TARGETS = ('Geometrical Tolerance.1', 'Geometrical Tolerance.2')


def safe_name(name):
    return name.replace(' ', '_').replace('.', '_')


def load_seed(name):
    path = V5 / 'report.json'
    assert path.is_file(), f'Missing V5 report: {path}'
    best = (json.loads(path.read_text(encoding='utf-8')).get(name) or {}).get('best') or {}
    assert 'box' in best, f'Missing V5 seed for {name}'
    return tuple(map(int, best['box']))


def neutral_strokes(image):
    b, g, r = (image[:, :, i].astype(np.int16) for i in range(3))
    low = np.minimum(np.minimum(b, g), r)
    high = np.maximum(np.maximum(b, g), r)
    return (((low >= 130) & ((high - low) <= 65)).astype(np.uint8) * 255)


def _line_support(mask, y, x1, x2, band=1):
    h, w = mask.shape
    x1, x2 = max(0, x1), min(w - 1, x2)
    if x2 < x1:
        return 0.0
    slab = mask[max(0, y - band):min(h, y + band + 1), x1:x2 + 1]
    return float(np.mean(np.any(slab > 0, axis=0)))


def _cap_support(mask, x, top, bottom):
    h, w = mask.shape
    slab = mask[max(0, top):min(h, bottom + 1), max(0, x - 2):min(w, x + 3)]
    return float(np.mean(np.any(slab > 0, axis=1))) if slab.size else 0.0


def _find_row_pair(mask, seed):
    x, y, sw, sh = seed
    h, w = mask.shape
    # Inspect horizontal lines around the known value cell.
    center_l = max(0, x + sw // 4)
    center_r = min(w - 1, x + 3 * sw // 4)
    candidates = []
    for top in range(max(0, y - 8), min(h, y + 10)):
        if _line_support(mask, top, center_l, center_r) < 0.75:
            continue
        for bottom in range(max(top + 12, y + sh - 10), min(h, y + sh + 10)):
            if _line_support(mask, bottom, center_l, center_r) < 0.75:
                continue
            proximity = abs(top - y) + abs(bottom - (y + sh - 1))
            score = (_line_support(mask, top, center_l, center_r)
                     + _line_support(mask, bottom, center_l, center_r)
                     - 0.04 * proximity)
            candidates.append((score, top, bottom))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1:]


def _outer_left_from_borders(horizontal, vertical, top, bottom, divider, seed_x):
    """Find a weak outer cap using BOTH horizontal-border endpoints.

    Only search within one plausible symbol cell left of the divider.
    No hardcoded screenshot coordinates are used.
    """
    h, w = horizontal.shape
    frame_h = bottom - top + 1
    lo = max(0, divider - int(0.85 * frame_h))
    hi = divider - max(5, int(0.22 * frame_h))
    candidates = []
    for xx in range(lo, hi + 1):
        # Frame border must run continuously from candidate to divider.
        top_cov = _line_support(horizontal, top, xx, divider, band=1)
        bottom_cov = _line_support(horizontal, bottom, xx, divider, band=1)
        if min(top_cov, bottom_cov) < 0.86:
            continue
        # Distinguish an actual outer endpoint from a point on a long leader line:
        # both horizontal strokes should start near the candidate.
        before_top = _line_support(horizontal, top, xx - 5, xx - 2, band=1)
        before_bottom = _line_support(horizontal, bottom, xx - 5, xx - 2, band=1)
        after_top = _line_support(horizontal, top, xx, xx + 4, band=1)
        after_bottom = _line_support(horizontal, bottom, xx, xx + 4, band=1)
        if min(after_top, after_bottom) < 0.70:
            continue
        if max(before_top, before_bottom) > 0.55:
            continue
        cap = _cap_support(vertical, xx, top, bottom)
        # Weak outer border is acceptable if BOTH border endpoints agree.
        if cap < 0.12:
            continue
        score = min(top_cov, bottom_cov) + cap + (1 - max(before_top, before_bottom))
        candidates.append((score, xx, cap))
    if not candidates:
        return None, []
    candidates.sort(reverse=True)
    return candidates[0][1], [(int(xx), round(float(cap), 3)) for _, xx, cap in candidates[:12]]


def recover_frame(image, seed):
    x, y, sw, sh = map(int, seed)
    h, w = image.shape[:2]
    if sw <= 0 or sh <= 0 or x < 0 or y < 0 or x + sw > w or y + sh > h:
        return None, {'reason': 'invalid seed'}

    neutral = neutral_strokes(image)
    horizontal = cv2.morphologyEx(neutral, cv2.MORPH_CLOSE,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)))
    vertical = cv2.morphologyEx(neutral, cv2.MORPH_CLOSE,
                                cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))
    pair = _find_row_pair(horizontal, (x, y, sw, sh))
    if pair is None:
        return None, {'reason': 'top/bottom border pair not detected'}
    top, bottom = pair

    # End caps must match the SAME pair of horizontal borders. Unlike V5.3,
    # the left search explicitly goes beyond the value cell's inner divider.
    left_limit = max(0, x - max(3 * sh, int(sw * 1.3)))
    right_limit = min(w - 1, x + sw + max(sh * 2, int(sw * 0.6)))
    caps = []
    for xx in range(left_limit, right_limit + 1):
        support = _cap_support(vertical, xx, top, bottom)
        if support < 0.53:
            continue
        if min(_line_support(horizontal, top, xx - 3, xx + 3),
               _line_support(horizontal, bottom, xx - 3, xx + 3)) < 0.30:
            continue
        caps.append((xx, support))

    # Merge adjacent x coordinates representing the same thick vertical stroke.
    groups = []
    for xx, support in caps:
        if groups and xx <= groups[-1][-1][0] + 2:
            groups[-1].append((xx, support))
        else:
            groups.append([(xx, support)])
    edges = [max(group, key=lambda t: t[1]) for group in groups]

    # Right boundary: nearest supported end cap after the seed value,
    # allowing for an extra datum cell. Avoid far-off view outlines.
    right_choices = []
    for rx, rs in edges:
        if rx < x + int(sw * 0.65):
            continue
        top_cov = _line_support(horizontal, top, x + sw // 2, rx)
        bottom_cov = _line_support(horizontal, bottom, x + sw // 2, rx)
        if min(top_cov, bottom_cov) < 0.70:
            continue
        right_choices.append((rx, rs, top_cov, bottom_cov))
    if not right_choices:
        return None, {'reason': 'right cap not detected', 'caps': edges}
    # Prefer outer right cap over inner divider, but don't cross discontinuities.
    right = max(right_choices, key=lambda z: z[0])[0]

    # Left boundary: search for the first outer cap to the LEFT of the seed.
    # Require continuous top AND bottom lines between candidate and seed.
    left_choices = []
    for lx, ls in edges:
        if lx >= x - 2:
            continue
        top_cov = _line_support(horizontal, top, lx, x + sw // 2)
        bottom_cov = _line_support(horizontal, bottom, lx, x + sw // 2)
        if min(top_cov, bottom_cov) < 0.78:
            continue
        # Symbol cell should have a plausible width relative to frame height.
        extra = x - lx
        if extra < max(8, int(0.35 * (bottom - top))):
            continue
        left_choices.append((lx, ls, top_cov, bottom_cov))
    if not left_choices:
        return None, {'reason': 'outer left cap not detected', 'caps': edges,
                      'top': top, 'bottom': bottom, 'right': right}

    # The nearest left cap can be the INTERNAL divider between the symbol
    # and value cells. Seek the outer cap about one frame-height to its left.
    # Allow narrower symbol cells (e.g. 16 px for a 31 px-high frame).
    # This remains a scale-relative constraint, not a fixed screen coordinate.
    frame_h = bottom - top + 1
    plausible = [c for c in left_choices
                 if 0.40 * frame_h <= x - c[0] <= 1.65 * frame_h]
    if not plausible:
        return None, {'reason': 'outer symbol cap not confidently located',
                      'left_candidates': left_choices, 'caps': edges,
                      'top': top, 'bottom': bottom, 'right': right}

    # Prefer the farther cap in the expected symbol-cell band, while checking
    # that both frame horizontals remain continuous all the way to the seed.
    # This avoids selecting the internal divider adjacent to the value text.
    left, left_s, lt, lb = min(plausible, key=lambda z: z[0])

    # If the selected cap is unusually close to the value seed, it may be
    # the symbol/value divider. Inspect the outer symbol cell independently.
    # CATIA sometimes renders the outer cap with gaps, so the original 0.53
    # full-height support threshold can miss it.
    refinement = {'attempted': False, 'candidates': []}
    if x - left < 0.65 * frame_h:
        refinement['attempted'] = True
        search_start = max(0, x - int(1.65 * frame_h))
        search_end = left - max(4, int(0.12 * frame_h))
        alternatives = []
        for xx in range(search_start, search_end + 1):
            vs = _cap_support(vertical, xx, top, bottom)
            if vs < 0.18:
                continue
            ts = _line_support(horizontal, top, xx, x + sw // 2)
            bs = _line_support(horizontal, bottom, xx, x + sw // 2)
            if min(ts, bs) < 0.72:
                continue
            # A real cap must touch both horizontal borders locally.
            top_join = _line_support(horizontal, top, xx - 2, xx + 2)
            bottom_join = _line_support(horizontal, bottom, xx - 2, xx + 2)
            if min(top_join, bottom_join) < 0.35:
                continue
            alternatives.append((xx, vs, ts, bs))
        # Nearby pixels belong to one stroke; prefer the strongest pixel.
        grouped = []
        for item in alternatives:
            if grouped and item[0] <= grouped[-1][-1][0] + 2:
                grouped[-1].append(item)
            else:
                grouped.append([item])
        distinct = [max(g, key=lambda item: item[1]) for g in grouped]
        refinement['candidates'] = [(xx, round(vs, 3)) for xx, vs, _, _ in distinct]
        if distinct:
            # Outermost supported cap in a plausible single-symbol-cell band.
            candidate = min(distinct, key=lambda item: item[0])
            left, left_s, lt, lb = candidate
            refinement['selected'] = left
        else:
            # Second, independent method: paired horizontal-border endpoints.
            # This catches weak vertical caps without blindly expanding pixels.
            border_left, border_candidates = _outer_left_from_borders(
                horizontal, vertical, top, bottom, left, x
            )
            refinement['border_endpoint_candidates'] = border_candidates
            if border_left is not None:
                left = border_left
                left_s = _cap_support(vertical, left, top, bottom)
                lt = _line_support(horizontal, top, left, x + sw // 2)
                lb = _line_support(horizontal, bottom, left, x + sw // 2)
                refinement['selected'] = left
                refinement['method'] = 'paired_horizontal_endpoints'
            else:
                # Fallback for a frame crossing a dimension extension line:
                # the left vertical is visible, but the bottom border is
                # offset/occluded. Verify a strong vertical AND a top join,
                # plus bottom join within a few rows (not an arbitrary crop).
                outer_candidates = []
                frame_h = bottom - top + 1
                for xx in range(max(0, left - int(0.85 * frame_h)),
                                left - max(5, int(0.20 * frame_h))):
                    vs = _cap_support(vertical, xx, top, bottom)
                    if vs < 0.72:
                        continue
                    top_join = _line_support(horizontal, top, xx, xx + 5, band=2)
                    bottom_join = max(
                        _line_support(horizontal, yy, xx, xx + 5, band=1)
                        for yy in range(bottom - 5, bottom + 4)
                    )
                    if top_join < 0.45 or bottom_join < 0.45:
                        continue
                    outer_candidates.append((xx, vs, top_join, bottom_join))
                refinement['vertical_outer_candidates'] = [
                    (xx, round(vs, 3), round(tj, 3), round(bj, 3))
                    for xx, vs, tj, bj in outer_candidates
                ]
                if outer_candidates:
                    left, left_s, lt, lb = min(
                        (c for c in outer_candidates
                         if c[2] >= 0.95 and c[3] >= 0.95),
                        key=lambda c: c[0],
                        default=max(outer_candidates, key=lambda c: (min(c[2], c[3]), c[1]))
                    )
                    refinement['selected'] = left
                    refinement['method'] = 'vertical_with_offset_bottom_join'
                else:
                    refinement['reason'] = 'outer border not verified; inner divider only'
                    return None, {'reason': refinement['reason'],
                              'top': top, 'bottom': bottom, 'right': right,
                              'inner_divider': left, 'outer_cap_refinement': refinement}

    box = (int(left), int(top), int(right - left + 1), int(bottom - top + 1))
    return box, {'top': top, 'bottom': bottom, 'left': left, 'right': right,
                 'left_support': round(left_s, 3), 'left_top_line': round(lt, 3),
                 'left_bottom_line': round(lb, 3), 'cap_count': len(edges),
                 'left_candidates': [(a, round(b, 3)) for a, b, _, _ in left_choices],
                 'selected_symbol_width_px': x - left,
                 'outer_cap_refinement': refinement,
                 'status_note': 'provisional frame; visual verification required'}


@pytest.mark.parametrize('name', TARGETS)
def test_nonsemantic_frame_expansion_v54(name):
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
              'diagnostic': info,
              'status': 'candidate_needs_visual_review' if box else 'needs_review'}
    (OUT / f'{safe}_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('\n' + json.dumps(report, indent=2))
    assert box is not None, f'Full GD&T frame not verified: {info}'
