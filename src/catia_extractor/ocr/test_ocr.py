
from pathlib import Path

import cv2
import pytesseract

# If Tesseract is not in PATH, uncomment:
# pytesseract.pytesseract.tesseract_cmd = (
#     r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# )

ROOT = Path(__file__).resolve().parents[3]

IMAGES_DIR = (
    ROOT / "output" / "pipeline_v2" / "annotations"
)


def test_ocr():
    images = sorted(
        IMAGES_DIR.glob("*/full_frame.png")
    )

    if not images:
        print("No full_frame.png found")
        return

    for image_path in images:
        print("\n------------------------")
        print("Annotation:", image_path.parent.name)

        image = cv2.imread(str(image_path))

        if image is None:
            print("Could not read image")
            continue

        # Prepare image for OCR
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        enlarged = cv2.resize(
            gray,
            None,
            fx=5,
            fy=5,
            interpolation=cv2.INTER_CUBIC
        )

        # OCR recognition
        text = pytesseract.image_to_string(
            enlarged,
            config="--oem 3 --psm 7"
        )

        print("Raw OCR:", repr(text.strip()))


if __name__ == "__main__":
    test_ocr()
