
"""Build the final CATIA engineering report.

Combines:
- Unified COM + Vision + OCR report
- Automatic engineering validation
- Human engineering approval

Does not modify original extraction reports.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from catia_extractor.pipeline_unified.human_review import (
    _fingerprint,
    _hash_file,
)

ROOT = Path(__file__).resolve().parents[3]

APPROVAL_DECISIONS = {
    "approved",
    "corrected_and_approved",
}

VALUE_FIELDS = (
    "geometric_symbol",
    "tolerance",
    "diameter_modifier",
    "material_condition_modifier",
    "datum_references",
)


def _read(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            f"Required report missing: {path}"
        )

    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _index(report: dict, source: str) -> dict:
    indexed = {}

    for record in report.get("results", []):
        key = record.get("annotation_id")

        if not key or key in indexed:
            raise ValueError(
                f"{source}: missing or duplicate annotation_id: {key!r}"
            )

        indexed[key] = record

    return indexed


def _same_path(a: str | None, b: Path) -> bool:
    return bool(a) and Path(a).resolve() == b.resolve()


def _ocr_values(item: dict) -> dict:
    ocr = item.get("ocr") or {}
    symbol = ocr.get("geometric_symbol") or {}
    tolerance = ocr.get("tolerance") or {}

    return {
        "geometric_symbol": symbol.get("glyph"),
        "tolerance": tolerance.get("raw"),
        "diameter_modifier": ocr.get("diameter_modifier"),
        "material_condition_modifier": ocr.get(
            "material_condition_modifier"
        ),
        "datum_references": ocr.get("datum_references"),
    }


def _valid_values(values: dict | None) -> bool:
    if not isinstance(values, dict):
        return False

    if set(values) != set(VALUE_FIELDS):
        return False

    symbol = values["geometric_symbol"]

    if not isinstance(symbol, str) or not symbol.strip():
        return False

    try:
        value = values["tolerance"]

        if isinstance(value, bool):
            return False

        tolerance = Decimal(
            str(value).strip().replace(",", ".")
        )

        if not tolerance.is_finite() or tolerance < 0:
            return False

    except (InvalidOperation, ValueError, TypeError):
        return False

    for field in (
        "diameter_modifier",
        "material_condition_modifier",
    ):
        modifier = values[field]

        if modifier is not None:
            if not isinstance(modifier, str):
                return False

            if not modifier.strip():
                return False

    datums = values["datum_references"]

    return isinstance(datums, list) and all(
        isinstance(d, str) and bool(d.strip())
        for d in datums
    )


def _save(path: Path, report: dict) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(".tmp")

    tmp.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def run(project_root=None) -> dict:

    root = (
        Path(project_root).resolve()
        if project_root
        else ROOT
    )

    folder = root / "output" / "pipeline_unified"

    unified_path = folder / "engineering_report.json"
    validation_path = folder / "validation_report.json"
    review_path = folder / "human_review_report.json"

    destination = (
        folder / "final_engineering_report.json"
    )

    # STEP 1: Load source reports

    unified = _read(unified_path)
    validation = _read(validation_path)
    review = _read(review_path)

    document = unified.get("document")

    if (
        not document
        or document != validation.get("document")
        or document != review.get("document")
    ):
        raise ValueError(
            "Reports refer to different CATIA documents."
        )

    # STEP 2: Match annotations by ID

    unified_rows = _index(unified, "Unified")
    validation_rows = _index(validation, "Validation")
    review_rows = _index(review, "Human review")

    if (
        set(unified_rows) != set(validation_rows)
        or set(unified_rows) != set(review_rows)
    ):
        raise ValueError(
            "Annotation IDs differ across reports. "
            "Rerun validation and human review."
        )

    source_run = (
        unified.get("run_utc")
        or validation.get("validated_at_utc")
        or "unknown"
    )

    global_issues = []

    if not _same_path(
        validation.get("source_report"),
        unified_path,
    ):
        global_issues.append(
            "VALIDATION_SOURCE_MISMATCH"
        )

    if not _same_path(
        review.get("source_validation_report"),
        validation_path,
    ):
        global_issues.append(
            "REVIEW_SOURCE_MISMATCH"
        )

    if review.get("source_run_utc") != source_run:
        global_issues.append(
            "REVIEW_FROM_ANOTHER_RUN"
        )

    results = []

    # STEP 3: Verify each annotation

    for annotation_id, item in unified_rows.items():

        check = validation_rows[annotation_id]
        signed = review_rows[annotation_id]

        issues = list(global_issues)

        original = _ocr_values(item)

        image_path = check.get("review_image")

        image_hash = (
            _hash_file(Path(image_path))
            if image_path
            else None
        )

        # Recalculate evidence fingerprint

        expected_fingerprint = _fingerprint(
            check,
            source_run,
            image_hash,
        )

        if check.get("extracted_values") != original:
            issues.append(
                "VALIDATION_VALUES_DIFFER_FROM_OCR"
            )

        if (
            item.get("full_frame") or {}
        ).get("image") != image_path:
            issues.append("FRAME_IMAGE_MISMATCH")

        if (
            check.get("status") == "blocked"
            or not check.get("automatic_checks_passed")
        ):
            issues.append(
                "AUTOMATIC_VALIDATION_BLOCKED"
            )

        if (
            not image_hash
            or signed.get("image_sha256") != image_hash
        ):
            issues.append(
                "IMAGE_CHANGED_OR_MISSING"
            )

        if (
            signed.get("evidence_fingerprint")
            != expected_fingerprint
        ):
            issues.append(
                "EVIDENCE_FINGERPRINT_CHANGED"
            )

        if (
            signed.get("original_values")
            != check.get("extracted_values")
        ):
            issues.append(
                "REVIEW_ORIGINAL_VALUES_MISMATCH"
            )

        if signed.get("review_image") != image_path:
            issues.append(
                "REVIEW_IMAGE_PATH_MISMATCH"
            )

        if (
            signed.get("validation_status")
            != check.get("status")
        ):
            issues.append(
                "REVIEW_VALIDATION_STATUS_MISMATCH"
            )

        # STEP 4: Check human approval

        decision = signed.get(
            "decision",
            "pending",
        )

        if (
            decision not in APPROVAL_DECISIONS
            or signed.get("engineering_approval") is not True
        ):
            issues.append("SIGN_OFF_MISSING")

        if (
            not signed.get("reviewer")
            or not signed.get("reviewed_at_utc")
        ):
            issues.append(
                "REVIEWER_OR_TIMESTAMP_MISSING"
            )

        if (
            check.get("issues")
            or decision == "corrected_and_approved"
        ) and not str(
            signed.get("notes") or ""
        ).strip():
            issues.append("REVIEW_NOTES_MISSING")

        reviewed = signed.get("reviewed_values")

        if not _valid_values(reviewed):
            issues.append("REVIEWED_VALUES_INVALID")

        elif (
            decision == "approved"
            and reviewed != original
        ):
            issues.append(
                "UNRECORDED_CORRECTION"
            )

        approved = not issues

        # STEP 5: Build final annotation record

        results.append({
            "annotation_id": annotation_id,
            "annotation_name": item.get(
                "annotation_name"
            ),
            "annotation_type": item.get(
                "annotation_type"
            ),
            "status": (
                decision if approved else "not_approved"
            ),
            "engineering_approval": approved,

            "com_metadata": item.get(
                "known_com_metadata", {}
            ),

            "full_frame": item.get(
                "full_frame", {}
            ),

            "ocr_original_values": original,
            "reviewed_values": reviewed,

            "final_values": (
                reviewed if approved else None
            ),

            "automatic_validation": {
                "status": check.get("status"),
                "issues": check.get("issues", []),
            },

            "human_review": {
                "decision": decision,
                "reviewer": signed.get("reviewer"),
                "reviewed_at_utc": signed.get(
                    "reviewed_at_utc"
                ),
                "notes": signed.get("notes"),
                "evidence_fingerprint": signed.get(
                    "evidence_fingerprint"
                ),
                "image_sha256": signed.get(
                    "image_sha256"
                ),
            },

            "approval_checks": {
                "passed": approved,
                "issues": issues,
            },
        })

    # STEP 6: Calculate global approval

    approved_count = sum(
        row["engineering_approval"]
        for row in results
    )

    all_approved = (
        bool(results)
        and approved_count == len(results)
        and review.get("engineering_approval") is True
    )

    # STEP 7: Create final report

    report = {
        "report_version": "final-engineering-v1",
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "document": document,
        "source_run_utc": source_run,

        "status": (
            "approved"
            if all_approved
            else "needs_review"
        ),

        "engineering_approval": all_approved,

        "sources": {
            "unified": str(unified_path),
            "validation": str(validation_path),
            "human_review": str(review_path),

            "com_extraction": unified.get(
                "sources", {}
            ).get("com_extraction"),

            "vision_report": unified.get(
                "sources", {}
            ).get("vision_report"),

            "ocr_report": unified.get(
                "sources", {}
            ).get("ocr_report"),
        },

        "summary": {
            "annotations": len(results),
            "approved": approved_count,

            "corrected_and_approved": sum(
                r["status"] == "corrected_and_approved"
                for r in results
            ),

            "not_approved": (
                len(results) - approved_count
            ),
        },

        "results": results,
    }

    _save(destination, report)

    # STEP 8: Terminal summary

    print(
        "\n========== FINAL ENGINEERING REPORT =========="
    )

    for row in results:
        print(
            f"{row['annotation_name']}: "
            f"{row['status']}"
        )

        for issue in row["approval_checks"]["issues"]:
            print("  -", issue)

    print(
        "Approved:",
        approved_count,
        "/",
        len(results),
    )

    print(
        "Engineering approval:",
        report["engineering_approval"],
    )

    print("Report:", destination)

    return report


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Build approved CATIA engineering report"
    )

    parser.add_argument(
        "--project-root",
        default=None,
    )

    args = parser.parse_args()

    run(args.project_root)
