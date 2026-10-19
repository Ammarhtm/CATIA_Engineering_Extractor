from typing import Any


def _is_present(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    return True


def analyze_missing_fields(
    required_fields: dict[str, list[str]],
    extracted_data: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Compare required fields with extracted values.

    required_fields:
        {annotation_id: [field_name, ...]}

    extracted_data:
        {annotation_id: {field_name: value, ...}}

    Missing fields become visual extraction candidates.
    No CATIA connection or image processing is performed here.
    """
    tasks = []

    for annotation_id, fields in required_fields.items():
        values = extracted_data.get(annotation_id, {})
        missing_fields = []

        for field in fields:
            if not _is_present(values.get(field)):
                missing_fields.append(field)

        if missing_fields:
            tasks.append({
                "annotation_id": annotation_id,
                "missing_fields": missing_fields,
                "status": "pending_visual_extraction",
                "engineering_approval": False,
            })

    return tasks
