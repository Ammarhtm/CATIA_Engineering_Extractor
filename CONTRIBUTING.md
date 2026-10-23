# Development workflow

Keep work modular and reviewable:

- CATIA COM and model extraction: `src/catia_extractor/catia/` and `pipeline_v1/`.
- Image detection/capture: `vision/` and `pipeline_v2/`.
- OCR/symbol recognition: `ocr/`.
- Reports, validation and exports: `pipeline_unified/`.
- User interface only: `frontend/`.

Suggested branch flow: `feature/<topic>` → offline tests → live-CATIA check on Windows → pull request → review/merge into `main`.

Before committing, run `python -m pytest -q` and `python scripts/check_project.py`, inspect `git diff --cached --name-only`, and confirm that no confidential CATParts, images or `output/` reports are staged. Keep a test log for any changed CATIA-specific algorithm. Avoid changing legacy reporting schemas without updating the corresponding consumers.

No contribution or distribution license is granted implicitly by the public presence of this repository.
