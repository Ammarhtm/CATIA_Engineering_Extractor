# Architecture and engineering traceability

## Modules and contracts

| Module | Role | Standalone entry point |
|---|---|---|
| `catia` | Live CATIA COM adapters; metadata/datum/dimension/GD&T extractors | Used by V1 |
| `pipeline_v1` | Read part data, report API extraction gaps | `python -m catia_extractor.pipeline_v1.runner` |
| `pipelines` | Shared gap-analysis and evidence support | Imported by V1 |
| `vision` | Desktop capture and selection-guided frame localization | Imported by V2 |
| `pipeline_v2` | Visual fallback from V1 tasks to full GD&T crops | `python -m catia_extractor.pipeline_v2.runner` |
| `ocr` | Cell segmentation, symbol templates, numeric and datum OCR | `python -m catia_extractor.ocr.run_from_pipeline2` |
| `pipeline_unified` | Orchestrate V1/V2/OCR; correlate by `annotation_id`; validate/review/finalize/export | `python -m catia_extractor.pipeline_unified.runner` |
| `frontend` | Tkinter workflow, image preview, review decisions, export format selection | `python -m catia_extractor.frontend.desktop_app` |

`pipeline_unified` is **not** a copy of V1 or V2. It calls the existing stage runners and correlates the resulting reports. `frontend` should not implement its own computer-vision or CATIA COM extraction logic.

## Primary contracts (runtime data)

1. `output/pipeline_v1/catia_full_extraction.json`: complete CATIA COM data, including extractor statuses, semantic and nonsemantic annotations, datums and dimensions.
2. `output/pipeline_v1/com_gap_report.json`: records whose displayed information could not be reliably extracted through COM.
3. `output/pipeline_v2/vision_report.json`: selection evidence, ranked frame candidates, provisional full-frame boxes and images.
4. `output/pipeline_v2/ocr_report.json`: raw OCR, extracted symbol/tolerance/modifiers/datum and segmentation evidence.
5. `output/pipeline_unified/engineering_report.json`: combined records keyed by `annotation_id`.
6. `output/pipeline_unified/validation_report.json`: automated checks, warnings/blockers, source image paths.
7. `output/pipeline_unified/human_review_report.json`: reviewer decisions, corrected values and fingerprinted evidence.
8. `output/pipeline_unified/final_engineering_report.json`: final values **only if** approval checks pass; otherwise `null`.
9. `output/engineering_export/engineering_export_complete.json`, `engineering_data.xlsx` and `csv/`: complete and tabular exports.

## Safety invariants

- A successful OCR read is **not** a human engineering approval.
- A numeric zero tolerance triggers further review rather than automatic acceptance.
- Annotations are joined by stable annotation IDs, not by row order or screen coordinates.
- Source OCR, reviewed values, validation warnings and sign-off metadata remain separately identifiable.
- Changes to a source image or evidence fingerprint invalidate previous approval for that evidence.
- Exporting a partially reviewed run is permitted, but unapproved data must retain that status.
- CATIA COM extraction and OCR geometry depend on CATIA presentation and may require further verification for unseen models.

## Scope boundary

The current pilot focused on two nonsemantic GD&T annotations in `Part_b.CATPart`. The COM inventory also includes other categories; an approval for two OCR records must not be interpreted as approval of the entire part or all inventoried annotations.
