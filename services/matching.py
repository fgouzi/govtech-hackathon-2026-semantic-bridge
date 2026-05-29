"""Semantic schema matching: embedding cosine + lexical + datatype heuristic."""

from __future__ import annotations

from rapidfuzz import fuzz

from core.logging import get_logger
from domain.concept import I14YConcept
from domain.mapping import FieldMapping, MappingPlan
from domain.schema import DataType, DatasetSchema, SchemaField
from services.embedding import EmbeddingService

log = get_logger(__name__)

_CONFIDENCE_THRESHOLD_AI = 0.70
_WEIGHT_EMBEDDING = 0.60
_WEIGHT_LEXICAL = 0.30
_WEIGHT_TYPE = 0.10

_TYPE_COMPAT: dict[DataType, set[DataType]] = {
    DataType.STRING: {DataType.STRING, DataType.UNKNOWN},
    DataType.INTEGER: {DataType.INTEGER, DataType.FLOAT, DataType.UNKNOWN},
    DataType.FLOAT: {DataType.FLOAT, DataType.INTEGER, DataType.UNKNOWN},
    DataType.DATE: {DataType.DATE, DataType.STRING, DataType.UNKNOWN},
    DataType.BOOLEAN: {DataType.BOOLEAN, DataType.UNKNOWN},
    DataType.UNKNOWN: set(DataType),
}


class SemanticMatchingService:
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self._embeddings = embedding_service

    def match_field(
        self,
        field: SchemaField,
        concepts: list[I14YConcept],
        top_k: int = 3,
    ) -> FieldMapping:
        if not concepts:
            return FieldMapping(source_field=field.name, confidence=0.0, method="no_concepts")

        # 1. Embedding similarity (top-k candidates)
        embedding_hits = self._embeddings.search(field.name, top_k=top_k)
        if not embedding_hits:
            # Fallback: lexical only across all concepts
            return self._lexical_only_match(field, concepts)

        best_mapping: FieldMapping | None = None
        best_score = -1.0

        for concept, emb_score in embedding_hits:
            lexical_score = fuzz.token_sort_ratio(
                field.name.lower().replace("_", " "),
                concept.name.lower().replace(".", " "),
            ) / 100.0

            # Also check aliases
            alias_score = max(
                (fuzz.token_sort_ratio(field.name.lower(), a.lower()) / 100.0 for a in concept.aliases),
                default=0.0,
            )
            lexical_score = max(lexical_score, alias_score)

            type_score = 1.0 if concept.data_type in _TYPE_COMPAT.get(field.data_type, set()) else 0.3

            combined = (
                _WEIGHT_EMBEDDING * emb_score
                + _WEIGHT_LEXICAL * lexical_score
                + _WEIGHT_TYPE * type_score
            )

            if combined > best_score:
                best_score = combined
                method = _determine_method(emb_score, lexical_score)
                best_mapping = FieldMapping(
                    source_field=field.name,
                    matched_concept=concept,
                    confidence=round(combined, 3),
                    method=method,
                )

        return best_mapping or FieldMapping(source_field=field.name, confidence=0.0)

    def match_schema(
        self,
        schema: DatasetSchema,
        concepts: list[I14YConcept],
    ) -> MappingPlan:
        mappings: list[FieldMapping] = []
        for field in schema.fields:
            mapping = self.match_field(field, concepts)
            mappings.append(mapping)
            log.debug(
                "field_matched",
                field=field.name,
                concept=mapping.matched_concept.name if mapping.matched_concept else None,
                confidence=mapping.confidence,
            )
        return MappingPlan(source_schema=schema, mappings=mappings)

    def _lexical_only_match(self, field: SchemaField, concepts: list[I14YConcept]) -> FieldMapping:
        best_concept: I14YConcept | None = None
        best_score = 0.0
        for concept in concepts:
            score = fuzz.token_sort_ratio(field.name.lower(), concept.name.lower()) / 100.0
            if score > best_score:
                best_score = score
                best_concept = concept
        return FieldMapping(
            source_field=field.name,
            matched_concept=best_concept,
            confidence=round(best_score * 0.9, 3),
            method="lexical",
        )


def _determine_method(emb_score: float, lex_score: float) -> str:
    if emb_score > 0.7 and lex_score > 0.6:
        return "embedding+lexical"
    if emb_score > 0.7:
        return "embedding"
    if lex_score > 0.6:
        return "lexical"
    return "heuristic"
