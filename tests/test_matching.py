"""Tests for semantic matching service."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from domain.concept import I14YConcept
from domain.schema import DataType, SchemaField
from services.embedding import EmbeddingService
from services.matching import SemanticMatchingService, _determine_method


class TestSemanticMatchingService:
    @pytest.fixture
    def mock_embedding(self, sample_concepts: list[I14YConcept]) -> EmbeddingService:
        """Create an EmbeddingService with mocked search that returns first concept."""
        service = MagicMock(spec=EmbeddingService)
        # Return (concept, high_score) for the first concept
        service.search.return_value = [(sample_concepts[0], 0.92)]
        return service  # type: ignore[return-value]

    @pytest.fixture
    def matching(self, mock_embedding: EmbeddingService) -> SemanticMatchingService:
        return SemanticMatchingService(mock_embedding)

    def test_match_obvious_field(
        self,
        matching: SemanticMatchingService,
        sample_concepts: list[I14YConcept],
        mock_embedding: MagicMock,
    ) -> None:
        # Configure mock to return full_name concept with high score
        mock_embedding.search.return_value = [(sample_concepts[0], 0.92)]
        field = SchemaField(name="full_name", data_type=DataType.STRING)
        result = matching.match_field(field, sample_concepts)
        assert result.matched_concept is not None
        assert result.confidence >= 0.7

    def test_match_returns_field_mapping(
        self,
        matching: SemanticMatchingService,
        sample_concepts: list[I14YConcept],
    ) -> None:
        field = SchemaField(name="birth_date", data_type=DataType.DATE)
        result = matching.match_field(field, sample_concepts)
        assert result.source_field == "birth_date"
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0

    def test_match_empty_concepts_returns_zero_confidence(
        self,
        matching: SemanticMatchingService,
    ) -> None:
        field = SchemaField(name="some_field", data_type=DataType.STRING)
        result = matching.match_field(field, [])
        assert result.confidence == 0.0
        assert result.matched_concept is None

    def test_match_schema_returns_plan(
        self,
        matching: SemanticMatchingService,
        sample_schema: object,
        sample_concepts: list[I14YConcept],
    ) -> None:
        from domain.schema import DatasetSchema
        assert isinstance(sample_schema, DatasetSchema)
        plan = matching.match_schema(sample_schema, sample_concepts)
        assert len(plan.mappings) == len(sample_schema.fields)
        assert plan.source_schema.name == sample_schema.name

    def test_type_compatibility_boosts_score(
        self,
        matching: SemanticMatchingService,
        sample_concepts: list[I14YConcept],
        mock_embedding: MagicMock,
    ) -> None:
        date_concept = next(c for c in sample_concepts if c.data_type == DataType.DATE)
        mock_embedding.search.return_value = [(date_concept, 0.75)]

        date_field = SchemaField(name="birth_date", data_type=DataType.DATE)
        int_field = SchemaField(name="birth_date", data_type=DataType.INTEGER)

        result_date = matching.match_field(date_field, sample_concepts)
        result_int = matching.match_field(int_field, sample_concepts)
        # DATE field should score higher with DATE concept
        assert result_date.confidence >= result_int.confidence


class TestDetermineMethod:
    def test_both_high(self) -> None:
        assert _determine_method(0.85, 0.75) == "embedding+lexical"

    def test_embedding_only(self) -> None:
        assert _determine_method(0.85, 0.4) == "embedding"

    def test_lexical_only(self) -> None:
        assert _determine_method(0.4, 0.75) == "lexical"

    def test_heuristic_fallback(self) -> None:
        assert _determine_method(0.4, 0.4) == "heuristic"
