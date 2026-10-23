
from pathlib import Path
import cv2

from catia_extractor.ocr.gdt_ocr import _detect_cells

ROOT = Path(__file__).resolve().parents[3]

INPUT_DIR = ROOT / "output" / "pipeline_v2" / "annotations"
OUTPUT_DIR = ROOT / "output" / "pipeline_v2" / "ocr_debug"


def test_segmentation():

    images = sorted(INPUT_DIR.glob("*/full_frame.png"))

    if not images:
        print("ERROR: No full_frame.png found")
        return

    for image_path in images:

        print("\n----------------------------")
        print("Annotation:", image_path.parent.name)

        image = cv2.imread(str(image_path))

        if image is None:
            print("ERROR: Cannot read image")
            continue

        cells, info = _detect_cells(image)

        if cells is None:
            print("SEGMENTATION FAILED")
            print(info)
            continue

        save_dir = OUTPUT_DIR / image_path.parent.name
        save_dir.mkdir(parents=True, exist_ok=True)

        names = ["symbol", "tolerance", "datum"]

        for index, (name, cell) in enumerate(
            zip(names, cells), start=1
        ):
            output_path = save_dir / f"cell_{index}_{name}.png"
            cv2.imwrite(str(output_path), cell)
            print(f"Cell {index}: {name} -> {cell.shape[1]}x{cell.shape[0]}")

        print("Boundaries:", info["bounds"])
        print("SEGMENTATION SUCCESS")


if __name__ == "__main__":
    test_segmentation()
