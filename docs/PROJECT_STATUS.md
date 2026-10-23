# Project status — Pilot V1

## Demonstrated end-to-end on one CATIA V5 pilot part

- COM extraction and gap analysis: 6 configured extractors reported successful, including part parameters/features, semantic and nonsemantic GD&T, dimensions, datums and reference frames.
- Visual fallback: 2 nonsemantic GD&T annotations localized with full-frame crops.
- OCR: both frames produced candidate fields for geometric symbol, tolerance, modifiers and datum references.
- Automatic validation: 1 annotation flagged for zero-tolerance / numeric OCR ambiguity; 1 passed the automatic checks and was ready for human review.
- Human review: 2 decisions explicitly approved on that pilot evidence (with reviewer identity and image hashes preserved in local reports).
- Export: Excel workbook with 17 worksheets, 17 CSV tables and a complete JSON data bundle, generated locally.

These outcomes are **pilot run observations, not generalized performance metrics**. Original engineering evidence and reviewer signatures are excluded from this source repository. New CATIA parts, view layouts, complex GD&T and different Windows configurations need separate validation before operational use.

## Follow-up research priorities

1. Test a broader range of GD&T symbols and modifiers, including multiple datum references and alternative formatting.
2. Quantify false positives in selection-guided frame detection and record OCR confidence on unseen files.
3. Add integration test fixtures cleared for publication (synthetic or non-proprietary only).
4. Improve error recovery and session management in the desktop application.
5. Package a Windows installer only after validating dependencies and COM deployment.
