# Testing strategy & limitations

## Verified offline checks

Run from the root of the repository:

```powershell
python -m compileall -q src/catia_extractor
python -m pytest -q
python scripts/check_project.py
```

`pytest` defaults to `tests/unit` and `tests/offline`. The second folder contains checks for review decisions, fingerprint invalidation, final-report gating and Excel writing. These tests use synthetic sample metadata and **do not require CATIA**.

## Integration / research scripts

`tests/integration/` contains historical experiments and probes of CATIA V5 COM/FTA interfaces, including work on OCR and geometric tolerances. They often require an active CATIA desktop, Windows-specific APIs, and a particular sample document. They are **opt-in** and are not a reliable portable CI test suite. Execute them individually after inspecting their preconditions, e.g.:

```powershell
python tests/integration/test_catia_connection.py
```

Default CI does not run live-CATIA tests. `CATIA V5` cannot be validated through the repository build runner, because it requires an interactive licensed CATIA session.

## What is not claimed

- End-to-end CATIA V5 integration cannot be confirmed by Linux/CI unit tests.
- Frame detection/OCR generalization to unseen CAD presentation styles is **not established** by the two-annotation pilot.
- Automatic checks verify internal consistency, not engineering design conformity.
- Publishing this source tree must not include captured proprietary CATIA screenshots or user-specific generated reports.
