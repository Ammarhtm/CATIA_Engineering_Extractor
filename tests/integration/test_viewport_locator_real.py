
import json
from pathlib import Path

import cv2

from catia_extractor.vision.viewport_locator import (
    detect_viewport,
    draw_viewport_candidate,
)


ROOT = Path(__file__).resolve().parents[2]

CANDIDATE_DIR = (
    ROOT
    / "output"
    / "pipeline_v2"
    / "annotations"
)


def test_viewport_on_real_catia_capture():
    images = sorted(CANDIDATE_DIR.rglob("after.png"))

    assert images, (
        f"No after.png screenshots found under {CANDIDATE_DIR}"
    )

    for image_path in images:
        bgr = cv2.imread(str(image_path))
        assert bgr is not None, f"Cannot read {image_path}"

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        detection = detect_viewport(rgb)

        preview = draw_viewport_candidate(rgb, detection)

        output_path = image_path.parent / "viewport_detection.png"

        assert cv2.imwrite(str(output_path), preview), (
            f"Cannot save diagnostic image: {output_path}"
        )

        report_path = image_path.parent / "viewport_detection.json"
        report_path.write_text(
            json.dumps(detection, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\nImage:", image_path)
        print("Detection:", detection)
        print("Preview:", output_path)

        # This integration test records the result for inspection.
        # A candidate ROI is not automatically considered correct.
