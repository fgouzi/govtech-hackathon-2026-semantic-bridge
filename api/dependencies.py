"""FastAPI dependency providers for shared services."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from adapters.cache import SQLiteCache
from adapters.mcp.client import MCPClient
from agents.interoperability_agent import InteroperabilityAgent
from core.config import Settings, get_settings
from domain.concept import I14YConcept
from services.comparison import DatasetComparisonService
from services.embedding import EmbeddingService
from services.mapping import MappingGenerationService
from services.matching import SemanticMatchingService
from services.schema_resolver import SchemaResolver
from services.shacl_matching import SHACLShapeMatcher
from services.transformation import TransformationEngine
from services.validation import ValidationEngine


def get_config() -> Settings:
    return get_settings()


def get_mcp_client(request: Request) -> MCPClient:
    return request.app.state.mcp_client  # type: ignore[no-any-return]


def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service  # type: ignore[no-any-return]


def get_concepts(request: Request) -> list[I14YConcept]:
    return request.app.state.concepts  # type: ignore[no-any-return]


def get_cache(request: Request) -> SQLiteCache:
    return request.app.state.cache  # type: ignore[no-any-return]


def get_matching_service(
    embedding: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> SemanticMatchingService:
    return SemanticMatchingService(embedding)


def get_mapping_service(
    matching: Annotated[SemanticMatchingService, Depends(get_matching_service)],
) -> MappingGenerationService:
    return MappingGenerationService(matching)


def get_transformation_engine() -> TransformationEngine:
    return TransformationEngine()


def get_validation_engine() -> ValidationEngine:
    return ValidationEngine()


def get_shacl_matcher(
    embedding: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> SHACLShapeMatcher:
    return SHACLShapeMatcher(embedding)


def get_agent() -> InteroperabilityAgent:
    return InteroperabilityAgent()


def get_schema_resolver(
    mcp: Annotated[MCPClient, Depends(get_mcp_client)],
) -> SchemaResolver:
    return SchemaResolver(mcp)


def get_comparison_service(
    mapping: Annotated[MappingGenerationService, Depends(get_mapping_service)],
    validation: Annotated[ValidationEngine, Depends(get_validation_engine)],
) -> DatasetComparisonService:
    return DatasetComparisonService(mapping, validation)
