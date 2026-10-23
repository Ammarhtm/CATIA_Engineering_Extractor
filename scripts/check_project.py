"""Offline release hygiene check: Python syntax, required files, forbidden artifact dirs."""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md", "pyproject.toml", ".gitignore",
    "src/catia_extractor/pipeline_v1/runner.py",
    "src/catia_extractor/pipeline_v2/runner.py",
    "src/catia_extractor/pipeline_unified/runner.py",
    "src/catia_extractor/pipeline_unified/engineering_validator.py",
    "src/catia_extractor/pipeline_unified/final_report.py",
    "src/catia_extractor/pipeline_unified/export_engineering.py",
    "src/catia_extractor/frontend/desktop_app.py",
    "src/catia_extractor/vision/full_frame_locator.py",
    "src/catia_extractor/ocr/gdt_ocr.py",
)


def main() -> int:
    issues = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            issues.append(f"Missing required file: {relative}")
    for folder in ("output", "datasets", "results"):
        if (ROOT / folder).exists():
            print(f"INFO: local {folder}/ exists; .gitignore must exclude it")
    files = list((ROOT / "src").rglob("*.py"))
    for file in files:
        data = file.read_bytes()
        if b"\0" in data:
            issues.append(f"Null bytes: {file.relative_to(ROOT)}")
            continue
        try:
            ast.parse(data.decode("utf-8-sig"), filename=str(file))
        except (SyntaxError, UnicodeError) as error:
            issues.append(f"Python source error: {file.relative_to(ROOT)}: {error}")
    print(f"Checked {len(files)} Python source modules and {len(REQUIRED)} required files")
    for error in issues:
        print("ERROR:", error)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
