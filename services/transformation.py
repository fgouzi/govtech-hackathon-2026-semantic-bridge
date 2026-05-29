"""Transformation engine: generate plans and apply them to records."""

from __future__ import annotations

from typing import Any

from core.exceptions import TransformationError
from core.logging import get_logger
from domain.mapping import MappingPlan
from domain.schema import DataType, DatasetSchema
from domain.transformation import TransformationPlan, TransformationRule

log = get_logger(__name__)


class TransformationEngine:
    def generate_plan(self, mapping: MappingPlan, target_schema: DatasetSchema | None = None) -> TransformationPlan:
        rules: list[TransformationRule] = []

        for fm in mapping.accepted_mappings():
            if fm.matched_concept is None:
                continue
            concept_name = fm.matched_concept.name
            source_field = fm.source_field

            # Determine operation based on type compatibility
            source_field_obj = next(
                (f for f in mapping.source_schema.fields if f.name == source_field), None
            )

            if source_field_obj and source_field_obj.data_type != fm.matched_concept.data_type:
                if fm.matched_concept.data_type == DataType.DATE:
                    rules.append(TransformationRule(
                        operation="cast",
                        source_field=source_field,
                        target_field=concept_name,
                        params={"to_type": "date", "format": "%Y-%m-%d"},
                    ))
                    continue
                elif fm.matched_concept.data_type in (DataType.INTEGER, DataType.FLOAT):
                    rules.append(TransformationRule(
                        operation="cast",
                        source_field=source_field,
                        target_field=concept_name,
                        params={"to_type": fm.matched_concept.data_type.value.lower()},
                    ))
                    continue

            rules.append(TransformationRule(
                operation="rename",
                source_field=source_field,
                target_field=concept_name,
            ))

        return TransformationPlan(
            rules=rules,
            source_schema=mapping.source_schema,
            target_schema=target_schema,
        )

    def apply(self, record: dict[str, Any], plan: TransformationPlan) -> dict[str, Any]:
        result: dict[str, Any] = dict(record)

        for rule in plan.rules:
            src = rule.source_field
            tgt = rule.target_field
            if src not in result:
                continue
            value = result.pop(src)

            try:
                if rule.operation == "rename":
                    result[tgt] = value
                elif rule.operation == "cast":
                    result[tgt] = _cast_value(value, rule.params)
                elif rule.operation == "normalize":
                    result[tgt] = str(value).strip().lower() if value is not None else value
                elif rule.operation == "concat":
                    other_field = rule.params.get("other_field", "")
                    sep = rule.params.get("sep", " ")
                    other_val = result.pop(other_field, "")
                    result[tgt] = f"{value}{sep}{other_val}"
                elif rule.operation == "split":
                    sep = rule.params.get("sep", " ")
                    idx = rule.params.get("index", 0)
                    parts = str(value).split(sep)
                    result[tgt] = parts[idx] if idx < len(parts) else value
                elif rule.operation == "identity":
                    result[tgt] = value
                else:
                    result[tgt] = value
            except Exception as exc:
                log.warning("transform_rule_failed", rule=rule.operation, field=src, error=str(exc))
                result[tgt] = value

        return result

    def apply_batch(
        self, records: list[dict[str, Any]], plan: TransformationPlan
    ) -> list[dict[str, Any]]:
        return [self.apply(r, plan) for r in records]


def _cast_value(value: Any, params: dict[str, Any]) -> Any:
    to_type = params.get("to_type", "string")
    if value is None:
        return None
    if to_type in ("int", "integer"):
        return int(float(str(value)))
    if to_type == "float":
        return float(str(value))
    if to_type == "date":
        import datetime  # noqa: PLC0415
        fmt = params.get("format", "%Y-%m-%d")
        try:
            return datetime.datetime.strptime(str(value), fmt).date().isoformat()
        except ValueError:
            return str(value)
    return str(value)
