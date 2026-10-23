
import json
from pathlib import Path

import cv2

from catia_extractor.vision.capture import selection_change_mask
from catia_extractor.vision.selection_guided_locator import (
    locate_selected_annotation_frame,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "debug" / "selection_guided_locator"


def find_capture_pairs():
    """Discover before/after screenshot pairs without fixed annotation names."""
    pairs = []

    for before_path in ROOT.rglob("before.png"):
        if any(
            part in {"venv", ".venv", ".git", "__pycache__"}
            for part in before_path.parts
        ):
            continue

        after_path = before_path.with_name("after.png")

        if after_path.is_file():
            pairs.append((before_path, after_path))

    return sorted(pairs)


def test_existing_catia_capture_pairs():
    pairs = find_capture_pairs()

    assert pairs, (
        "No matching before.png/after.png pairs found. "
        "Check the existing dynamic_capture output directory."
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for before_path, after_path in pairs:
        before_bgr = cv2.imread(str(before_path))
        after_bgr = cv2.imread(str(after_path))

        assert before_bgr is not None, f"Cannot read {before_path}"
        assert after_bgr is not None, f"Cannot read {after_path}"

        before_rgb = cv2.cvtColor(before_bgr, cv2.COLOR_BGR2RGB)
        after_rgb = cv2.cvtColor(after_bgr, cv2.COLOR_BGR2RGB)

        result = locate_selected_annotation_frame(
            before_rgb,
            after_rgb,
        )

        mask = selection_change_mask(before_rgb, after_rgb)

        safe_name = before_path.parent.name or before_path.stem
        output_dir = OUTPUT_DIR / safe_name
        output_dir.mkdir(parents=True, exist_ok=True)

        cv2.imwrite(str(output_dir / "selection_mask.png"), mask)

        report = {
            "before_image": str(before_path),
            "after_image": str(after_path),
            **result,
        }

        (output_dir / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\nAnnotation capture:", before_path.parent)
        print("Selection pixels:", result["selected_pixel_count"])
        print("Status:", result["status"])
        print("Frame candidates:", len(result["candidates"]))
        print("Report:", output_dir / "report.json")
