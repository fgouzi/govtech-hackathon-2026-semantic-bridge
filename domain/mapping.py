from pydantic import BaseModel, Field, computed_field

from domain.concept import I14YConcept
from domain.schema import DatasetSchema


class FieldMapping(BaseModel):
    source_field: str
    matched_concept: I14YConcept | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = "embedding+lexical"
    explanation: str | None = None

    @property
    def is_accepted(self) -> bool:
        return self.matched_concept is not None and self.confidence >= 0.5


class MappingPlan(BaseModel):
    source_schema: DatasetSchema
    mappings: list[FieldMapping]

    @computed_field  # type: ignore[misc]
    @property
    def overall_confidence(self) -> float:
        if not self.mappings:
            return 0.0
        return round(sum(m.confidence for m in self.mappings) / len(self.mappings), 3)

    def accepted_mappings(self) -> list[FieldMapping]:
        return [m for m in self.mappings if m.is_accepted]

    def unmatched_fields(self) -> list[str]:
        return [m.source_field for m in self.mappings if not m.is_accepted]
