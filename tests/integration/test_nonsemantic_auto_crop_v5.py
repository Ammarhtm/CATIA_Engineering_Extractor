
from pathlib import Path
import time
import json

import cv2
import numpy as np
import pyautogui
import win32con
import win32gui

from catia_extractor.catia.connection import connect_to_catia


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "debug" / "nonsemantic_v5"

TARGETS = [
    "Geometrical Tolerance.1",
    "Geometrical Tolerance.2",
]


def find_annotation(part, name):
    for s in range(1, part.AnnotationSets.Count + 1):
        ann_set = part.AnnotationSets.Item(s)

        for i in range(1, ann_set.Annotations.Count + 1):
            ann = ann_set.Annotations.Item(i)

            if ann.Name == name:
                return ann

    raise AssertionError(f"Annotation not found: {name}")


def find_catia_window(document_name):
    matches = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd)

        if (
            "CATIA V5" in title.upper()
            and document_name.lower() in title.lower()
        ):
            matches.append(hwnd)

    win32gui.EnumWindows(callback, None)

    assert len(matches) == 1, (
        f"Expected one CATIA window, found {len(matches)}"
    )

    return matches[0]


def prepare_window(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(1)

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception as exc:
        print("Foreground request:", repr(exc))

    time.sleep(1)

    assert not win32gui.IsIconic(hwnd)

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    screen_w, screen_h = pyautogui.size()

    x1 = max(0, left)
    y1 = max(0, top)
    x2 = min(screen_w, right)
    y2 = min(screen_h, bottom)

    assert x2 - x1 > 300
    assert y2 - y1 > 200

    return (x1, y1, x2 - x1, y2 - y1)


def capture(region):
    return np.asarray(
        pyautogui.screenshot(region=region).convert("RGB")
    )


def selection_change_mask(before, after):
    hsv = cv2.cvtColor(after, cv2.COLOR_RGB2HSV)

    orange = cv2.inRange(
        hsv,
        np.array([4, 110, 110], dtype=np.uint8),
        np.array([28, 255, 255], dtype=np.uint8),
    )

    diff = cv2.absdiff(before, after)
    changed = np.max(diff, axis=2) > 45

    return np.where(
        (orange > 0) & changed, 255, 0
    ).astype(np.uint8)


def detect_frame_geometry(before):
    """
    Detect GD&T frame geometry from the clean screenshot.
    Diagnostic version: keep plausible boxes and report
    geometry measurements instead of rejecting too early.
    """
    gray = cv2.cvtColor(before, cv2.COLOR_RGB2GRAY)
    bright = cv2.inRange(gray, 145, 255)

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (12, 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, 8)
    )

    horizontal = cv2.morphologyEx(
        bright, cv2.MORPH_OPEN, horizontal_kernel
    )
    vertical = cv2.morphologyEx(
        bright, cv2.MORPH_OPEN, vertical_kernel
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

    height, width = gray.shape
    candidates = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        if not (30 <= w <= min(350, width)):
            continue
        if not (10 <= h <= 90):
            continue

        aspect = w / max(h, 1)
        if not (1.5 <= aspect <= 20):
            continue

        if y < int(height * 0.10):
            continue
        if y + h > int(height * 0.94):
            continue

        h_roi = horizontal[y:y + h, x:x + w]
        v_roi = vertical[y:y + h, x:x + w]

        # Relaxed measurements; do not reject candidates here.
        horizontal_rows = int(np.count_nonzero(
            np.count_nonzero(h_roi, axis=1) >= 0.35 * w
        ))

        vertical_cols = int(np.count_nonzero(
            np.count_nonzero(v_roi, axis=0) >= 0.35 * h
        ))

        candidates.append({
            "box": (int(x), int(y), int(w), int(h)),
            "aspect": round(float(aspect), 3),
            "horizontal_rows": horizontal_rows,
            "vertical_cols": vertical_cols,
        })

    return lines, candidates


def overlap_ratio(box, mask, padding=5):
    x, y, w, h = box
    height, width = mask.shape

    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(width, x + w + padding)
    y2 = min(height, y + h + padding)

    roi = mask[y1:y2, x1:x2]

    if roi.size == 0:
        return 0.0

    return float(np.count_nonzero(roi) / roi.size)


def score_candidates(candidates, selection_mask):
    scored = []

    for candidate in candidates:
        overlap = overlap_ratio(
            candidate["box"],
            selection_mask,
            padding=4,
        )

        h_rows = candidate["horizontal_rows"]
        v_cols = candidate["vertical_cols"]

        geometry_score = (
            0.5 * min(h_rows / 2.0, 1.0)
            + 0.5 * min(v_cols / 3.0, 1.0)
        )

        selection_score = min(overlap * 20, 1.0)

        score = (
            0.60 * selection_score
            + 0.40 * geometry_score
        )

        scored.append({
            **candidate,
            "selection_overlap": round(overlap, 5),
            "score": round(float(score), 4),
        })

    # Prefer candidates actually linked to the orange selection.
    # Pure geometry-only rectangles are diagnostic, not reliable seeds.
    scored.sort(
        key=lambda item: (
            item["selection_overlap"] >= 0.005,
            item["score"],
        ),
        reverse=True,
    )

    return scored


def save_crop(image, box, path):
    x, y, w, h = box

    margin_x = 10
    margin_y = 8

    height, width = image.shape[:2]

    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(width, x + w + margin_x)
    y2 = min(height, y + h + margin_y)

    crop = image[y1:y2, x1:x2]

    cv2.imwrite(
        str(path),
        cv2.cvtColor(crop, cv2.COLOR_RGB2BGR),
    )


def test_nonsemantic_auto_crop_v5():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    session = connect_to_catia()
    document = session.document
    part = document.Part
    selection = document.Selection

    hwnd = find_catia_window(document.Name)
    region = prepare_window(hwnd)

    print("\nCATIA region:", region)

    results = {}

    try:
        for name in TARGETS:
            selection.Clear()
            time.sleep(0.8)

            before = capture(region)

            selection.Add(find_annotation(part, name))
            time.sleep(0.8)

            after = capture(region)

            selection_mask = selection_change_mask(
                before, after
            )

            geometry_mask, geometric_candidates = (
                detect_frame_geometry(before)
            )

            scored = score_candidates(
                geometric_candidates,
                selection_mask,
            )

            print("\n====== DIAGNOSTIC V5 ======")
            print("Annotation:", name)
            print("Geometric candidates:", len(geometric_candidates))
            print("Scored candidates:", len(scored))
            print("Selection pixels:", cv2.countNonZero(selection_mask))

            for index, candidate in enumerate(scored[:15], start=1):
                print(
                    f"#{index} "
                    f"box={candidate['box']} "
                    f"H={candidate['horizontal_rows']} "
                    f"V={candidate['vertical_cols']} "
                    f"overlap={candidate['selection_overlap']:.5f} "
                    f"score={candidate['score']:.4f}"
                )

            safe = name.replace(" ", "_").replace(".", "_")

            # Clean full screenshots, required by V5.1.
            cv2.imwrite(
                str(OUTPUT / f"{safe}_before.png"),
                cv2.cvtColor(before, cv2.COLOR_RGB2BGR),
            )
            cv2.imwrite(
                str(OUTPUT / f"{safe}_after.png"),
                cv2.cvtColor(after, cv2.COLOR_RGB2BGR),
            )

            cv2.imwrite(
                str(OUTPUT / f"{safe}_selection_mask.png"),
                selection_mask,
            )
            cv2.imwrite(
                str(OUTPUT / f"{safe}_geometry_mask.png"),
                geometry_mask,
            )

            debug = cv2.cvtColor(
                after, cv2.COLOR_RGB2BGR
            )

            print(f"\n====== {name} ======")
            print(
                "Geometric candidates:",
                len(geometric_candidates),
            )
            print("Matched candidates:", len(scored))

            for index, candidate in enumerate(
                scored[:10], start=1
            ):
                x, y, w, h = candidate["box"]

                color = (
                    (0, 255, 0)
                    if index == 1
                    else (0, 255, 255)
                )

                cv2.rectangle(
                    debug,
                    (x, y),
                    (x + w, y + h),
                    color,
                    2,
                )

                cv2.putText(
                    debug,
                    f"{index}: {candidate['score']:.2f}",
                    (x, max(15, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    1,
                )

                save_crop(
                    before,
                    candidate["box"],
                    OUTPUT / f"{safe}_candidate_{index}.png",
                )

                print(
                    f"#{index}: "
                    f"box={candidate['box']} "
                    f"score={candidate['score']} "
                    f"overlap={candidate['selection_overlap']}"
                )

            status = "needs_review"

            if scored:
                best = scored[0]

                # Experimental acceptance threshold.
                if (
                    best["score"] >= 0.55
                    and best["selection_overlap"] >= 0.005
                    and best["horizontal_rows"] >= 2
                    and best["vertical_cols"] >= 2
                    ):
                    status = "candidate_needs_review"

                    save_crop(
                        before,
                        best["box"],
                        OUTPUT / f"{safe}_best_crop.png",
                    )

            results[name] = {
                "status": status,
                "candidate_count": len(scored),
                "best": scored[0] if scored else None,
                "candidates": scored[:15],
                "before_image": str(OUTPUT / f"{safe}_before.png"),
                "after_image": str(OUTPUT / f"{safe}_after.png"),
            }

            cv2.imwrite(
                str(OUTPUT / f"{safe}_debug.png"),
                debug,
            )

            print("Status:", status)

    finally:
        selection.Clear()

    report_path = OUTPUT / "report.json"

    report_path.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )

    print("\n====== SUMMARY ======")

    for name, result in results.items():
        print(
            name,
            "->",
            result["status"],
        )

    print("Report:", report_path.resolve())

    assert len(results) == len(TARGETS)
