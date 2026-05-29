from typing import Any, Literal

from pydantic import BaseModel

from domain.schema import DatasetSchema

OperationType = Literal["rename", "cast", "concat", "split", "normalize", "identity"]


class TransformationRule(BaseModel):
    operation: OperationType
    source_field: str
    target_field: str
    params: dict[str, Any] = {}


class TransformationPlan(BaseModel):
    rules: list[TransformationRule]
    source_schema: DatasetSchema
    target_schema: DatasetSchema | None = None

    def describe(self) -> str:
        lines = [f"Transformation plan ({len(self.rules)} rules):"]
        for rule in self.rules:
            lines.append(f"  {rule.operation}: {rule.source_field} → {rule.target_field}")
        return "\n".join(lines)


class ValidationIssue(BaseModel):
    field: str
    issue: str
    detail: str
    severity: Literal["error", "warning"]


class ValidationReport(BaseModel):
    passed: bool
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    @property
    def summary(self) -> str:
        return f"{len(self.warnings)} warning(s), {len(self.errors)} error(s)"
