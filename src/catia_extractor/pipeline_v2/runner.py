
"""Pipeline 2 - CATIA Visual GD&T Frame Extraction.

Input:
    output/pipeline_v1/com_gap_report.json

Outputs:
    output/pipeline_v2/vision_report.json
    output/pipeline_v2/annotations/<annotation_id>/
        before.png
        after.png
        selection_mask.png
        diagnostic_overlay.png
        candidate_*.png
        full_frame.png                 (when localized)
        full_frame_diagnostic.png      (when localized)
        report.json

Important:
    COM selects the annotation.
    Orange changes provide association evidence.
    C1 is a seed, not necessarily a complete frame.
    Full-frame detection uses clean image geometry.
    Engineering data is never automatically approved.
"""



from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from catia_extractor.catia.connection import connect_to_catia
from catia_extractor.vision.capture import (
    find_catia_window,
    prepare_window,
    capture,
    selection_change_mask,
)
from catia_extractor.vision.frame_locator import (
    locate_frame_candidates,
    save_crop,
)
from catia_extractor.vision.full_frame_locator import expand_to_full_frame


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[3]

GAP_REPORT = (
    ROOT / "output" / "pipeline_v1" / "com_gap_report.json"
)

OUTPUT_DIR = ROOT / "output" / "pipeline_v2"
ANNOTATIONS_DIR = OUTPUT_DIR / "annotations"
REPORT_PATH = OUTPUT_DIR / "vision_report.json"

PIPELINE_VERSION = "2.2-full-frame"

# These are relative geometric parameters, not CATIA coordinates.
FRAME_CONFIG = {
    "search_rows_factor": 0.20,
    "max_frame_width_factor": 12.0,
    "max_frame_width_pixels": 550,
    "min_vertical_border_ratio": 0.45,
    "min_horizontal_coverage": 0.72,
    "max_border_alignment_pixels": 5,
}


# ============================================================
# FILE UTILITIES
# ============================================================

def safe_filename(value: str) -> str:
    name = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        str(value),
    )
    return name.strip(" .") or "unnamed_annotation"


def save_rgb(path: Path, rgb_image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    bgr = cv2.cvtColor(
        rgb_image,
        cv2.COLOR_RGB2BGR,
    )

    if not cv2.imwrite(str(path), bgr):
        raise OSError(f"Cannot write image: {path}")


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def to_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): to_json(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [to_json(v) for v in value]

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, np.generic):
        return value.item()

    return value


# ============================================================
# PIPELINE 1 GAP REPORT
# ============================================================

def load_tasks(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing Pipeline 1 gap report: {path}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    gaps = data.get("gaps")

    if not isinstance(gaps, list):
        raise ValueError(
            "com_gap_report.json must contain a gaps list."
        )

    tasks = []

    for item in gaps:
        if not isinstance(item, dict):
            continue

        name = item.get("annotation_name")
        missing = item.get("missing_fields")

        if not isinstance(name, str) or not name.strip():
            continue

        if not isinstance(missing, list) or not missing:
            continue

        name = name.strip()

        tasks.append({
            "annotation_name": name,
            "annotation_id": str(
                item.get("annotation_id")
                or f"nonsemantic_gdt:{name}"
            ),
            "annotation_type": item.get("annotation_type"),
            "missing_fields": missing,
            "known_metadata": item.get("known_metadata", {}),
        })

    return tasks


# ============================================================
# CATIA COM ANNOTATION LOOKUP
# ============================================================

def find_annotation_objects(part, annotation_name: str):
    matches = []

    annotation_sets = part.AnnotationSets

    for s in range(1, annotation_sets.Count + 1):
        ann_set = annotation_sets.Item(s)
        annotations = ann_set.Annotations

        for i in range(1, annotations.Count + 1):
            annotation = annotations.Item(i)

            try:
                name = str(annotation.Name).strip()
            except Exception:
                continue

            if name.casefold() == annotation_name.casefold():
                matches.append(annotation)

    if not matches:
        raise LookupError(
            f"Annotation not found: {annotation_name}"
        )

    if len(matches) > 1:
        raise LookupError(
            f"Ambiguous annotation name: {annotation_name}"
        )

    return matches[0]


# ============================================================
# SELECTION REGIONS
# ============================================================

def get_selection_regions(mask):
    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    result = []

    for contour in contours:
        area = cv2.contourArea(contour)

        if area < 10:
            continue

        x, y, w, h = cv2.boundingRect(contour)

        result.append({
            "box": [int(x), int(y), int(w), int(h)],
            "contour_area": round(float(area), 2),
        })

    result.sort(
        key=lambda item: (
            item["box"][2] * item["box"][3]
        ),
        reverse=True,
    )

    return result


# ============================================================
# FRAME IMAGE PROCESSING
# ============================================================

def make_frame_line_mask(before_rgb):
    """Detect pale/white CAD strokes on CATIA's dark background.

    Uses brightness and low saturation to avoid magenta
    geometry and most orange selection highlights.
    """
    hsv = cv2.cvtColor(
        before_rgb,
        cv2.COLOR_RGB2HSV,
    )

    saturation = hsv[:, :, 1]
    brightness = hsv[:, :, 2]

    # More permissive than V2.2 for anti-aliased CAD lines.
    mask = np.where(
        (brightness >= 115)
        & (saturation <= 145),
        255,
        0,
    ).astype(np.uint8)

    return mask


def horizontal_line_mask(binary):
    """Bridge small anti-aliasing gaps in horizontal strokes."""
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (7, 1),
    )

    return cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        kernel,
    )


def row_segments(row):
    """Return foreground intervals as [start, end-exclusive]."""
    foreground = (row > 0).astype(np.uint8)

    padded = np.pad(
        foreground,
        (1, 1),
        constant_values=0,
    )

    changes = np.diff(
        padded.astype(np.int16)
    )

    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)

    return [
        (int(start), int(end))
        for start, end in zip(starts, ends)
    ]


def horizontal_border_candidates(
    hmask,
    seed_box,
    expected_y,
):
    """Find long horizontal strokes passing through seed.

    The seed is usually the tolerance-value cell,
    so the full top and bottom frame borders may
    extend both left and right of it.
    """
    image_h, image_w = hmask.shape[:2]

    sx, sy, sw, sh = (
        int(v) for v in seed_box
    )

    search_radius = max(
        3,
        round(
            sh * FRAME_CONFIG[
                "search_rows_factor"
            ]
        ),
    )

    max_width = min(
        FRAME_CONFIG["max_frame_width_pixels"],
        max(
            sw + 10,
            round(
                sh
                * FRAME_CONFIG[
                    "max_frame_width_factor"
                ]
            ),
        ),
    )

    seed_left = sx
    seed_right = sx + sw

    found = []

    for y in range(
        max(0, expected_y - search_radius),
        min(image_h, expected_y + search_radius + 1),
    ):
        for x1, x2 in row_segments(hmask[y]):
            width = x2 - x1

            if width < sw * 0.8:
                continue

            if width > max_width:
                continue

            overlap = max(
                0,
                min(x2, seed_right)
                - max(x1, seed_left),
            )

            if overlap < sw * 0.55:
                continue

            found.append({
                "y": int(y),
                "left": int(x1),
                "right": int(x2),
                "width": int(width),
                "seed_coverage": round(
                    overlap / max(sw, 1),
                    4,
                ),
            })

    found.sort(
        key=lambda item: (
            -item["seed_coverage"],
            -item["width"],
            abs(item["y"] - expected_y),
        )
    )

    return found


def vertical_border_ratio(
    binary,
    x,
    top,
    bottom,
    tolerance=2,
):
    """Measure how much of a vertical frame wall exists."""
    image_h, image_w = binary.shape[:2]

    x1 = max(0, x - tolerance)
    x2 = min(image_w, x + tolerance + 1)

    y1 = max(0, top)
    y2 = min(image_h, bottom + 1)

    if x1 >= x2 or y1 >= y2:
        return 0.0

    strip = binary[y1:y2, x1:x2] > 0

    row_support = np.any(strip, axis=1)

    return float(np.mean(row_support))


def border_coverage(
    binary,
    y,
    left,
    right,
    tolerance=2,
):
    """Check support for the horizontal outer frame border."""
    image_h, image_w = binary.shape[:2]

    y1 = max(0, y - tolerance)
    y2 = min(image_h, y + tolerance + 1)

    x1 = max(0, left)
    x2 = min(image_w, right)

    if y1 >= y2 or x1 >= x2:
        return 0.0

    strip = binary[y1:y2, x1:x2] > 0

    column_support = np.any(strip, axis=0)

    return float(np.mean(column_support))


# ============================================================
# DIAGNOSTIC OVERLAY
# ============================================================

def create_diagnostic_overlay(
    before_rgb,
    selection_mask,
    candidates,
    full_frame,
    output_path,
):
    preview = cv2.cvtColor(
        before_rgb,
        cv2.COLOR_RGB2BGR,
    )

    # Orange selection-change pixels.
    pixels = selection_mask > 0

    if np.any(pixels):
        preview[pixels] = (
            preview[pixels].astype(np.float32)
            * 0.35
            + np.array(
                [0, 140, 255],
                dtype=np.float32,
            )
            * 0.65
        ).astype(np.uint8)

    # Other candidates stay yellow.
    # The selected seed is green.
    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        x, y, w, h = (
            int(v) for v in candidate["box"]
        )

        associated = (
            candidate.get("selection_association")
            == "overlap_supported"
        )

        color = (
            (0, 255, 0)
            if associated
            else (0, 200, 255)
        )

        cv2.rectangle(
            preview,
            (x, y),
            (x + w, y + h),
            color,
            2,
        )

        cv2.putText(
            preview,
            f"C{index}",
            (x, max(16, y - 7)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )

    # Blue: complete candidate frame.
    if full_frame and full_frame.get("box"):
        x, y, w, h = full_frame["box"]

        cv2.rectangle(
            preview,
            (x, y),
            (x + w, y + h),
            (255, 0, 0),
            2,
        )

        cv2.putText(
            preview,
            "FULL FRAME",
            (x, max(16, y - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 0, 0),
            2,
        )

    if not cv2.imwrite(
        str(output_path),
        preview,
    ):
        raise OSError(
            f"Cannot save overlay: {output_path}"
        )


# ============================================================
# PROCESS ONE ANNOTATION
# ============================================================

def process_task(
    document,
    part,
    selection,
    region,
    task: dict[str, Any],
):
    annotation_id = task["annotation_id"]

    task_dir = (
        ANNOTATIONS_DIR
        / safe_filename(annotation_id)
    )

    task_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = {
        **task,
        "status": "pending",
        "selection_confirmed": False,
        "selection_changed_pixels": 0,
        "selection_regions": [],
        "frame_candidates": [],
        "selected_seed": None,
        "full_frame": None,
        "frame_association_established": False,
        "associated_candidate_count": 0,
        "error": None,
        "engineering_approval": False,
    }

    # Prevent old successful-looking crops from remaining
    # when the current run fails to find a full frame.
    for old_file in (
        "full_frame.png",
        "full_frame_diagnostic.png",
    ):
        path = task_dir / old_file
        if path.exists():
            path.unlink()

    try:
        # 1. Resolve annotation dynamically.
        annotation = find_annotation_objects(
            part,
            task["annotation_name"],
        )

        # 2. Clean baseline screenshot.
        selection.Clear()
        time.sleep(0.35)

        before = capture(region)

        save_rgb(
            task_dir / "before.png",
            before,
        )

        # 3. Select COM annotation.
        selection.Add(annotation)
        time.sleep(0.55)

        after = capture(region)

        save_rgb(
            task_dir / "after.png",
            after,
        )

        # 4. Orange selection evidence.
        mask = selection_change_mask(
            before,
            after,
        )

        if not cv2.imwrite(
            str(task_dir / "selection_mask.png"),
            mask,
        ):
            raise OSError(
                "Could not save selection mask."
            )

        changed_pixels = int(
            cv2.countNonZero(mask)
        )

        result["selection_changed_pixels"] = (
            changed_pixels
        )

        result["selection_confirmed"] = (
            changed_pixels > 0
        )

        result["selection_regions"] = (
            get_selection_regions(mask)
        )

        # 5. Detect candidate cells in clean screenshot.
        candidates = locate_frame_candidates(
            before,
            selection_mask=(
                mask
                if changed_pixels > 0
                else None
            ),
        )

        for i, candidate in enumerate(
            candidates,
            start=1,
        ):
            candidate_data = to_json(
                candidate
            )

            candidate_data["candidate_index"] = i
            candidate_data["crop_file"] = (
                f"candidate_{i}.png"
            )

            result["frame_candidates"].append(
                candidate_data
            )

            save_crop(
                before,
                candidate["box"],
                task_dir / f"candidate_{i}.png",
            )

        associated = [
            (i, candidate)
            for i, candidate in enumerate(
                candidates,
                start=1,
            )
            if candidate.get("selection_association")
            == "overlap_supported"
        ]

        result["associated_candidate_count"] = (
            len(associated)
        )

        result["frame_association_established"] = (
            bool(associated)
        )

        full_frame = None

        # 6. Select best associated candidate as seed.
        if associated:
            associated.sort(
                key=lambda pair: (
                    float(
                        pair[1].get(
                            "selection_overlap",
                            0.0,
                        )
                    ),
                    float(
                        pair[1].get(
                            "geometry_score",
                            0.0,
                        )
                    ),
                ),
                reverse=True,
            )

            seed_index, seed = associated[0]

            result["selected_seed"] = {
                "candidate_index": seed_index,
                "box": to_json(seed["box"]),
                "selection_overlap": seed.get(
                    "selection_overlap",
                    0.0,
                ),
            }

            # 7. Expand the seed into a full GD&T frame.
            full_frame = expand_to_full_frame(
                before,
                seed,
            )

            result["full_frame"] = full_frame

            if full_frame.get("box"):
                box = full_frame["box"]

                save_crop(
                    before,
                    box,
                    task_dir / "full_frame.png",
                )

                create_diagnostic_overlay(
                    before,
                    mask,
                    candidates,
                    full_frame,
                    task_dir / "full_frame_diagnostic.png",
                )

        # 8. Always save general diagnostic.
        create_diagnostic_overlay(
            before,
            mask,
            candidates,
            full_frame,
            task_dir / "diagnostic_overlay.png",
        )

        # Preserve the original preview filename.
        create_diagnostic_overlay(
            before,
            mask,
            candidates,
            full_frame,
            task_dir / "detected_frames.png",
        )

        # 9. Conservative statuses.
        if changed_pixels == 0:
            result["status"] = (
                "selection_not_visually_confirmed"
            )

        elif not candidates:
            result["status"] = (
                "no_frame_candidate"
            )

        elif not associated:
            result["status"] = (
                "frame_association_not_established"
            )

        elif (
            full_frame is not None
            and full_frame.get("box")
        ):
            result["status"] = (
                "full_frame_candidate_needs_review"
            )

        else:
            result["status"] = (
                "full_frame_not_established"
            )

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = repr(exc)

    finally:
        try:
            selection.Clear()
        except Exception:
            pass

        save_json(
            task_dir / "report.json",
            result,
        )

    return result


# ============================================================
# RUN PIPELINE
# ============================================================

def run_pipeline():
    tasks = load_tasks(GAP_REPORT)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    ANNOTATIONS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not tasks:
        report = {
            "pipeline_version": PIPELINE_VERSION,
            "source_gap_report": str(GAP_REPORT),
            "tasks_received": 0,
            "tasks_succeeded": 0,
            "tasks_failed": 0,
            "results": [],
            "status": "no_visual_tasks",
            "engineering_approval": False,
        }

        save_json(REPORT_PATH, report)
        return report

    # Connect to the currently running CATIA V5.
    session = connect_to_catia()

    document = session.document
    part = document.Part

    hwnd = find_catia_window(
        str(document.Name)
    )

    region = prepare_window(hwnd)

    selection = document.Selection

    print("\n========== PIPELINE 2 V2.2 ==========")
    print("Document:", document.Name)
    print("Tasks:", len(tasks))

    results = []

    try:
        for index, task in enumerate(
            tasks,
            start=1,
        ):
            print(
                f"\n[{index}/{len(tasks)}] "
                f"{task['annotation_name']}"
            )

            result = process_task(
                document=document,
                part=part,
                selection=selection,
                region=region,
                task=task,
            )

            results.append(result)

            print("Status:", result["status"])
            print(
                "Changed pixels:",
                result["selection_changed_pixels"],
            )
            print(
                "Associated candidates:",
                result["associated_candidate_count"],
            )

            frame = result.get("full_frame")

            if frame and frame.get("box"):
                print(
                    "Full frame box:",
                    frame["box"],
                )
            else:
                print(
                    "Full frame box: NOT ESTABLISHED"
                )

    finally:
        try:
            selection.Clear()
        except Exception:
            pass

    failures = sum(
        item["status"] == "failed"
        for item in results
    )

    full_frame_candidates = sum(
        item["status"]
        == "full_frame_candidate_needs_review"
        for item in results
    )

    report = {
        "pipeline_version": PIPELINE_VERSION,
        "document": str(document.Name),
        "source_gap_report": str(GAP_REPORT),
        "tasks_received": len(tasks),
        "tasks_succeeded": 0,
        "tasks_with_full_frame_candidate": (
            full_frame_candidates
        ),
        "tasks_failed": failures,
        "results": results,
        "status": "needs_review",
        "engineering_approval": False,
    }

    # A geometrically detected frame is not yet an
    # engineering-validated annotation.
    save_json(
        REPORT_PATH,
        report,
    )

    save_json(
        REPORT_PATH,
        report,
    )

    # ==========================================
    # NEW: AUTOMATIC GD&T OCR EXTRACTION
    # ==========================================

    print("\n========== GD&T OCR ==========")

    try:
        from catia_extractor.ocr.run_from_pipeline2 import (
            run as run_ocr,
        )

        ocr_report = run_ocr(project_root=ROOT)

        print(
            "OCR frames:",
            ocr_report.get(
                "frames_with_ocr_candidates", 0
            ),
        )

        print("OCR extraction completed.")

    except Exception as exc:
        print("WARNING: OCR extraction failed!")
        print("Error:", repr(exc))

    # ==========================================
    # ORIGINAL PIPELINE RESULTS
    # ==========================================

    print("\n========== RESULTS ==========")


    print("\n========== RESULTS ==========")
    print("Tasks:", len(tasks))
    print(
        "Full frame candidates:",
        full_frame_candidates,
    )
    print("Failed:", failures)
    print("Engineering approval: False")
    print("Report:", REPORT_PATH)

    return report


if __name__ == "__main__":
    run_pipeline()
