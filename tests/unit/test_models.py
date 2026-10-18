
import unittest

from catia_extractor.domain.models import (
    AnnotationRecord,
    DataSource,
    ExtractionResult,
    SourceEvidence,
    ValidationStatus,
)


class TestDomainModels(unittest.TestCase):

    def test_annotation_creation(self):
        annotation = AnnotationRecord(
            annotation_id="ANN_001",
            name="Position.1",
            annotation_type="position",
            tolerance_value=0.2,
            datums=["A", "B", "C"],
        )

        self.assertEqual(
            annotation.tolerance_value, 0.2
        )
        self.assertEqual(
            annotation.datums, ["A", "B", "C"]
        )
        self.assertEqual(
            annotation.validation_status,
            ValidationStatus.RAW,
        )

    def test_source_evidence(self):
        evidence = SourceEvidence(
            source=DataSource.OCR_3D,
            raw_value="0.2",
            confidence=0.95,
            bounding_box=(10, 20, 100, 40),
        )

        self.assertEqual(
            evidence.source, DataSource.OCR_3D
        )
        self.assertEqual(evidence.confidence, 0.95)

    def test_invalid_confidence(self):
        with self.assertRaises(ValueError):
            SourceEvidence(
                source=DataSource.OCR_3D,
                confidence=1.5,
            )

    def test_extraction_result(self):
        result = ExtractionResult(
            pipeline_name="COM",
        )

        result.annotations.append(
            AnnotationRecord(annotation_id="ANN_002")
        )

        self.assertEqual(
            len(result.annotations), 1
        )


if __name__ == "__main__":
    unittest.main()
