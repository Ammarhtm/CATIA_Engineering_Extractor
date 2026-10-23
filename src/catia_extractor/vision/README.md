# Vision primitives (Stage 1)

This package extracts reusable desktop-capture and GD&T frame-candidate detection
logic from the original V5 integration test.

## API

- `find_catia_window(document_name)` — find a visible CATIA V5 window by title.
- `prepare_window(hwnd)` — restore/foreground the window and compute a bounded screen region.
- `capture(region)` — capture that region as an RGB NumPy array.
- `selection_change_mask(before, after)` — identify changed pixels matching the CATIA orange selection range.
- `detect_frame_geometry(rgb_image)` — return a binary line mask and plausible frame candidates.
- `score_candidates(candidates, selection_mask)` — rank candidates using selection overlap and geometry.
- `locate_frame_candidates(rgb_image, selection_mask=None)` — convenience detection/ranking entry point.
- `save_crop(rgb_image, box, path)` — save a padded candidate crop.

## Important limitations

1. The detector returns geometric candidates, not a guaranteed annotation-to-frame match.
2. Selection-based ranking requires a before/after capture around selecting a specific CATIA annotation.
3. `find_catia_window`, `prepare_window`, and `capture` require a Windows desktop session, CATIA, `pywin32`, and `pyautogui`; imports are lazy so unit tests can run elsewhere.
4. The old integration test still uses two pilot annotation names. That is retained only for reproducing the original experiment; production orchestration must enumerate annotations dynamically in a later stage.
5. This stage does not run OCR or template matching and does not approve engineering data.

Run image-only tests from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/unit/test_vision_frame_locator.py -v
```
