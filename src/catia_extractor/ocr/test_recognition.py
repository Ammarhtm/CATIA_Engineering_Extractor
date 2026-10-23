
from pathlib import Path

from catia_extractor.ocr.gdt_ocr import extract_gdt_image

ROOT = Path(__file__).resolve().parents[3]

INPUT_DIR = ROOT / "output" / "pipeline_v2" / "annotations"

TEMPLATES = Path(__file__).resolve().parent / "templates"


def main():

    required = [
        "perpendicularity.png",
        "flatness.png",
        "diameter.png",
        "mmc.png"
    ]

    missing = [
        name for name in required
        if not (TEMPLATES / name).is_file()
    ]

    if missing:
        print("Missing templates:", missing)
        return

    images = sorted(INPUT_DIR.glob("*/full_frame.png"))

    if not images:
        print("No full frame images found")
        return

    for image_path in images:

        print("\n" + "=" * 45)
        print("ANNOTATION:", image_path.parent.name)

        result = extract_gdt_image(
            image_path,
            template_dir=TEMPLATES
        )

        symbol = result.get("geometric_symbol") or {}
        tolerance = result.get("tolerance") or {}

        print("Status:", result["status"])
        print("Symbol:", symbol.get("name"))
        print("Tolerance:", tolerance.get("raw"))
        print("Diameter:", result.get("diameter_modifier"))
        print("Material:", result.get("material_condition_modifier"))
        print("Datums:", result.get("datum_references"))
        print("Warnings:", result.get("warnings"))

        print("Engineering approval:",
              result["engineering_approval"])


if __name__ == "__main__":
    main()
