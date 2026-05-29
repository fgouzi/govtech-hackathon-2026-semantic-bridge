"""Mapping generation between two dataset schemas via shared I14Y concepts."""

from __future__ import annotations

from domain.concept import I14YConcept
from domain.mapping import FieldMapping, MappingPlan
from domain.schema import DatasetSchema
from services.matching import SemanticMatchingService


class MappingGenerationService:
    def __init__(self, matching_service: SemanticMatchingService) -> None:
        self._matching = matching_service

    def generate_bridge_mapping(
        self,
        source: DatasetSchema,
        target: DatasetSchema,
        concepts: list[I14YConcept],
    ) -> tuple[MappingPlan, MappingPlan]:
        """Map both schemas to concepts; the shared concepts form a bridge."""
        source_plan = self._matching.match_schema(source, concepts)
        target_plan = self._matching.match_schema(target, concepts)
        return source_plan, target_plan

    def find_join_candidates(
        self, source_plan: MappingPlan, target_plan: MappingPlan
    ) -> list[tuple[str, str, str]]:
        """Return (source_field, target_field, concept_name) triples for shared concepts."""
        source_concepts = {
            m.matched_concept.id: m.source_field
            for m in source_plan.accepted_mappings()
            if m.matched_concept
        }
        candidates: list[tuple[str, str, str]] = []
        for target_mapping in target_plan.accepted_mappings():
            if target_mapping.matched_concept and target_mapping.matched_concept.id in source_concepts:
                source_field = source_concepts[target_mapping.matched_concept.id]
                candidates.append(
                    (
                        source_field,
                        target_mapping.source_field,
                        target_mapping.matched_concept.name,
                    )
                )
        return candidates
