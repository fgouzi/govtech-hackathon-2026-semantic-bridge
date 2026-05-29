"""Validation engine: detect mapping issues and produce a structured report."""

from __future__ import annotations

from domain.mapping import MappingPlan
from domain.schema import DataType
from domain.transformation import ValidationIssue, ValidationReport

_LOW_CONFIDENCE_THRESHOLD = 0.70
_CRITICAL_CONFIDENCE = 0.50

_TYPE_INCOMPATIBLE: set[tuple[DataType, DataType]] = {
    # (source_type, concept_type) pairs that are incompatible
    (DataType.DATE, DataType.INTEGER),
    (DataType.DATE, DataType.FLOAT),
    (DataType.INTEGER, DataType.DATE),
    (DataType.FLOAT, DataType.DATE),
    (DataType.BOOLEAN, DataType.DATE),
    (DataType.BOOLEAN, DataType.FLOAT),
    (DataType.DATE, DataType.BOOLEAN),
}


class ValidationEngine:
    def validate(self, plan: MappingPlan) -> ValidationReport:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        seen_concepts: dict[str, str] = {}

        for mapping in plan.mappings:
            field = mapping.source_field

            # No match found
            if mapping.matched_concept is None:
                errors.append(ValidationIssue(
                    field=field,
                    issue="missing_mapping",
                    detail=f"Field '{field}' has no matching I14Y concept",
                    severity="error",
                ))
                continue

            concept = mapping.matched_concept

            # Low confidence (warning zone)
            if _CRITICAL_CONFIDENCE <= mapping.confidence < _LOW_CONFIDENCE_THRESHOLD:
                warnings.append(ValidationIssue(
                    field=field,
                    issue="low_confidence",
                    detail=f"Confidence {mapping.confidence:.2f} below threshold {_LOW_CONFIDENCE_THRESHOLD}",
                    severity="warning",
                ))

            # Very low confidence (error zone)
            if mapping.confidence < _CRITICAL_CONFIDENCE:
                errors.append(ValidationIssue(
                    field=field,
                    issue="low_confidence",
                    detail=f"Confidence {mapping.confidence:.2f} critically low (< {_CRITICAL_CONFIDENCE})",
                    severity="error",
                ))

            # Type incompatibility
            source_field_obj = next(
                (f for f in plan.source_schema.fields if f.name == field), None
            )
            if source_field_obj:
                pair = (source_field_obj.data_type, concept.data_type)
                if pair in _TYPE_INCOMPATIBLE:
                    warnings.append(ValidationIssue(
                        field=field,
                        issue="type_mismatch",
                        detail=(
                            f"Source type {source_field_obj.data_type.value} "
                            f"may be incompatible with concept type {concept.data_type.value}"
                        ),
                        severity="warning",
                    ))

            # Duplicate concept target
            if concept.id in seen_concepts:
                warnings.append(ValidationIssue(
                    field=field,
                    issue="duplicate_target",
                    detail=(
                        f"Concept '{concept.name}' already mapped from '{seen_concepts[concept.id]}'"
                    ),
                    severity="warning",
                ))
            else:
                seen_concepts[concept.id] = field

        return ValidationReport(
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
