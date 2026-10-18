
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DataSource(str, Enum):
    COM = "COM"
    OCR_TREE = "OCR_TREE"
    OCR_3D = "OCR_3D"


class ValidationStatus(str, Enum):
    RAW = "raw"
    VALIDATED = "validated"
    TO_REVIEW = "to_review"
    CONFLICT = "conflict"


@dataclass
class SourceEvidence:
    source: DataSource
    raw_value: Optional[str] = None
    confidence: Optional[float] = None

    capture_path: Optional[str] = None
    bounding_box: Optional[tuple[int, int, int, int]] = None

    catia_object_id: Optional[str] = None
    view_name: Optional[str] = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.confidence is not None:
            if not 0.0 <= self.confidence <= 1.0:
                raise ValueError(
                    "confidence must be between 0 and 1"
                )


@dataclass
class AnnotationRecord:
    annotation_id: str

    name: Optional[str] = None
    annotation_type: Optional[str] = None

    nominal_value: Optional[float] = None
    tolerance_value: Optional[float] = None

    symbol: Optional[str] = None
    datums: list[str] = field(default_factory=list)
    unit: Optional[str] = None

    evidence: list[SourceEvidence] = field(
        default_factory=list
    )

    validation_status: ValidationStatus = (
        ValidationStatus.RAW
    )

    extra_data: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class ExtractionResult:
    pipeline_name: str

    annotations: list[AnnotationRecord] = field(
        default_factory=list
    )

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass
class FusionResult:
    annotations: list[AnnotationRecord] = field(
        default_factory=list
    )

    conflicts: list[dict[str, Any]] = field(
        default_factory=list
    )

    unmatched_com: list[AnnotationRecord] = field(
        default_factory=list
    )

    unmatched_ocr: list[AnnotationRecord] = field(
        default_factory=list
    )
