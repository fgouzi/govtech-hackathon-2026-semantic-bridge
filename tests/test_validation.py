"""Tests for validation engine."""

import pytest

from domain.concept import I14YConcept
from domain.mapping import FieldMapping, MappingPlan
from domain.schema import DataType, DatasetSchema, SchemaField
from services.validation import ValidationEngine


@pytest.fixture
def engine() -> ValidationEngine:
    return ValidationEngine()


@pytest.fixture
def concept_string() -> I14YConcept:
    return I14YConcept(
        id="person.full_name",
        name="Person.FullName",
        description="Full name",
        data_type=DataType.STRING,
    )


@pytest.fixture
def concept_date() -> I14YConcept:
    return I14YConcept(
        id="person.dob",
        name="Person.DateOfBirth",
        description="Date of birth",
        data_type=DataType.DATE,
    )


class TestValidationEngine:
    def test_valid_plan_passes(
        self, engine: ValidationEngine, sample_mapping_plan: MappingPlan
    ) -> None:
        # sample_mapping_plan has 3 accepted + 1 unmatched (low confidence)
        report = engine.validate(sample_mapping_plan)
        # unmatched field should produce an error
        assert not report.passed or len(report.errors) > 0

    def test_all_good_mappings_pass(
        self,
        engine: ValidationEngine,
        concept_string: I14YConcept,
        concept_date: I14YConcept,
    ) -> None:
        schema = DatasetSchema(
            name="test",
            fields=[
                SchemaField(name="name", data_type=DataType.STRING),
                SchemaField(name="birth_date", data_type=DataType.DATE),
            ],
        )
        plan = MappingPlan(
            source_schema=schema,
            mappings=[
                FieldMapping(source_field="name", matched_concept=concept_string, confidence=0.92),
                FieldMapping(source_field="birth_date", matched_concept=concept_date, confidence=0.95),
            ],
        )
        report = engine.validate(plan)
        assert report.passed
        assert len(report.errors) == 0

    def test_missing_mapping_produces_error(
        self, engine: ValidationEngine, concept_string: I14YConcept
    ) -> None:
        schema = DatasetSchema(
            name="test",
            fields=[
                SchemaField(name="name", data_type=DataType.STRING),
                SchemaField(name="unknown_field", data_type=DataType.STRING),
            ],
        )
        plan = MappingPlan(
            source_schema=schema,
            mappings=[
                FieldMapping(source_field="name", matched_concept=concept_string, confidence=0.9),
                FieldMapping(source_field="unknown_field", matched_concept=None, confidence=0.0),
            ],
        )
        report = engine.validate(plan)
        assert not report.passed
        missing = [e for e in report.errors if e.issue == "missing_mapping"]
        assert len(missing) == 1
        assert missing[0].field == "unknown_field"

    def test_low_confidence_produces_warning(
        self, engine: ValidationEngine, concept_string: I14YConcept
    ) -> None:
        schema = DatasetSchema(
            name="test",
            fields=[SchemaField(name="name", data_type=DataType.STRING)],
        )
        plan = MappingPlan(
            source_schema=schema,
            mappings=[
                FieldMapping(source_field="name", matched_concept=concept_string, confidence=0.62),
            ],
        )
        report = engine.validate(plan)
        low_conf = [w for w in report.warnings if w.issue == "low_confidence"]
        assert len(low_conf) == 1

    def test_type_mismatch_produces_warning(
        self, engine: ValidationEngine, concept_date: I14YConcept
    ) -> None:
        schema = DatasetSchema(
            name="test",
            fields=[SchemaField(name="birth_year", data_type=DataType.INTEGER)],
        )
        plan = MappingPlan(
            source_schema=schema,
            mappings=[
                FieldMapping(
                    source_field="birth_year",
                    matched_concept=concept_date,
                    confidence=0.80,
                ),
            ],
        )
        report = engine.validate(plan)
        type_issues = [w for w in report.warnings if w.issue == "type_mismatch"]
        assert len(type_issues) == 1

    def test_duplicate_concept_produces_warning(
        self, engine: ValidationEngine, concept_string: I14YConcept
    ) -> None:
        schema = DatasetSchema(
            name="test",
            fields=[
                SchemaField(name="field_a", data_type=DataType.STRING),
                SchemaField(name="field_b", data_type=DataType.STRING),
            ],
        )
        plan = MappingPlan(
            source_schema=schema,
            mappings=[
                FieldMapping(source_field="field_a", matched_concept=concept_string, confidence=0.9),
                FieldMapping(source_field="field_b", matched_concept=concept_string, confidence=0.85),
            ],
        )
        report = engine.validate(plan)
        dups = [w for w in report.warnings if w.issue == "duplicate_target"]
        assert len(dups) == 1
        assert dups[0].field == "field_b"

    def test_report_summary(self, engine: ValidationEngine, sample_mapping_plan: MappingPlan) -> None:
        report = engine.validate(sample_mapping_plan)
        assert isinstance(report.summary, str)
        assert "error" in report.summary.lower()
