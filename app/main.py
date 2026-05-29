"""FastAPI application factory with lifespan for resource initialisation."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from adapters.cache import SQLiteCache
from adapters.mcp.client import MCPClient
from api.routes import compare, harmonize, health, match, search, shacl_match, transform, validate
from core.config import get_settings
from core.logging import configure_logging, get_logger
from domain.concept import I14YConcept
from services.embedding import EmbeddingService

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()

    # Cache
    cache = SQLiteCache(settings.cache_db_path)
    await cache.initialize()
    app.state.cache = cache

    # MCP client
    mcp_client = MCPClient(
        primary_url=settings.i14y_mcp_url,
        fallback_url=settings.mock_mcp_url,
        cache=cache,
    )
    await mcp_client._transport.__aenter__()
    await mcp_client.connect()
    app.state.mcp_client = mcp_client

    # Load concepts from MCP
    concepts = await _load_concepts(mcp_client)
    app.state.concepts = concepts
    log.info("concepts_loaded", count=len(concepts))

    # Embedding service + FAISS index
    embedding_service = EmbeddingService(settings.faiss_index_path)
    if not embedding_service.load_index(concepts):
        embedding_service.build_index(concepts)
    app.state.embedding_service = embedding_service

    log.info("semantic_bridge_ready", mcp_mode="live" if mcp_client.is_live else "mock")

    yield

    await cache.close()
    await mcp_client._transport.__aexit__(None, None, None)
    log.info("semantic_bridge_shutdown")


async def _load_concepts(client: MCPClient) -> list[I14YConcept]:
    """Fetch I14Y concepts via MCP.

    On live server: uses list_concepts + full_text_search_resources.
    On mock server: uses search_concepts with category queries.
    """
    if client.is_live:
        return await _load_concepts_live(client)
    return await _load_concepts_mock(client)


async def _load_concepts_live(client: MCPClient) -> list[I14YConcept]:
    """Load concepts from the real I14Y MCP server."""
    seen: dict[str, I14YConcept] = {}

    # 1. list_concepts — paginated list of all I14Y data concepts
    try:
        result = await client.call_tool("list_concepts", {"page": 1, "pageSize": 50})
        text = result.text()
        if text:
            data = json.loads(text)
            for raw in _extract_items(data):
                concept = _i14y_raw_to_concept(raw)
                if concept:
                    seen[concept.id] = concept
        log.info("i14y_concepts_listed", count=len(seen))
    except Exception as exc:
        log.warning("i14y_list_concepts_failed", error=str(exc))

    # 2. full_text_search for key interoperability terms
    search_terms = ["person", "address", "municipality", "organisation", "date of birth", "postal code"]
    for term in search_terms:
        try:
            result = await client.call_tool("full_text_search_resources", {"query": term})
            text = result.text()
            if not text:
                continue
            data = json.loads(text)
            for raw in _extract_items(data):
                concept = _i14y_raw_to_concept(raw)
                if concept and concept.id not in seen:
                    seen[concept.id] = concept
        except Exception as exc:
            log.debug("i14y_search_failed", term=term, error=str(exc))

    log.info("i14y_concepts_loaded", count=len(seen), mode="live")
    return list(seen.values())


async def _load_concepts_mock(client: MCPClient) -> list[I14YConcept]:
    """Load concepts from the local mock MCP server."""
    queries = ["person", "address", "organisation", "municipality", "date", "identifier"]
    seen: dict[str, I14YConcept] = {}

    for query in queries:
        try:
            result = await client.call_tool("search_concepts", {"query": query})
            text = result.text()
            if not text:
                continue
            data = json.loads(text)
            for raw in data.get("concepts", []):
                concept = I14YConcept.model_validate(raw)
                seen[concept.id] = concept
        except Exception as exc:
            log.warning("mock_concept_load_error", query=query, error=str(exc))

    log.info("mock_concepts_loaded", count=len(seen))
    return list(seen.values())


def _extract_items(data: dict | list) -> list[dict]:
    """Extract concept items from I14Y response shapes.

    I14Y list_concepts returns: {"pagination": ..., "data": {"data": [...]}}
    full_text_search_resources may return: {"data": [...]} or flat list.
    """
    if isinstance(data, list):
        return data  # type: ignore[return-value]
    # Unwrap nested data.data.data pattern from list_concepts
    inner = data.get("data", data)
    if isinstance(inner, dict):
        inner = inner.get("data", inner)
    if isinstance(inner, list):
        return inner  # type: ignore[return-value]
    # Fallback: try common keys
    for key in ("items", "results", "concepts", "value"):
        if key in data and isinstance(data[key], list):
            return data[key]  # type: ignore[return-value]
    return []


def _i14y_raw_to_concept(raw: dict) -> I14YConcept | None:
    """Map a raw I14Y API concept object to our I14YConcept domain model.

    I14Y concept fields:
      id: UUID string
      identifier: OID or short identifier (e.g. "2.16.756...")
      name: {"de": ..., "fr": ..., "en": ...}
      description: {"de": ..., "fr": ..., "en": ...}
      conceptType: "CodeList" | "DataElement" | etc.
      codeListEntryValueType: "String" | "Integer" | "Date" | etc.
    """
    from domain.schema import DataType  # noqa: PLC0415
    try:
        concept_id = raw.get("id") or raw.get("identifier") or raw.get("uuid")
        if not concept_id:
            return None

        name = _i14y_multilang(raw.get("name")) or str(raw.get("identifier", concept_id))
        description = _i14y_multilang(raw.get("description")) or _i14y_multilang(raw.get("comment")) or ""
        uri = str(raw.get("identifier") or raw.get("id") or "")
        category = str(raw.get("conceptType") or raw.get("type") or "")

        # Data type: prefer codeListEntryValueType, then xsdType, then conceptType
        raw_type = (
            raw.get("codeListEntryValueType")
            or raw.get("xsdType")
            or raw.get("dataType")
            or ""
        ).upper()
        data_type = _map_data_type(raw_type)

        # Build aliases from name variants and identifier
        aliases: list[str] = []
        name_obj = raw.get("name", {})
        if isinstance(name_obj, dict):
            aliases = [v for v in name_obj.values() if isinstance(v, str) and v != name]

        return I14YConcept(
            id=str(concept_id),
            name=name,
            description=description,
            data_type=data_type,
            uri=uri,
            category=category,
            aliases=aliases[:5],
        )
    except Exception:
        return None


def _i14y_multilang(value: object) -> str:
    """Extract a string from I14Y multilingual objects like {'de': '...', 'fr': '...'}."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return (
            value.get("de")
            or value.get("fr")
            or value.get("it")
            or value.get("en")
            or next(iter(value.values()), "")
            or ""
        )
    return ""


def _map_data_type(raw: str) -> "DataType":
    from domain.schema import DataType  # noqa: PLC0415
    mapping = {
        "DATE": DataType.DATE,
        "DATETIME": DataType.DATE,
        "INTEGER": DataType.INTEGER,
        "INT": DataType.INTEGER,
        "LONG": DataType.INTEGER,
        "FLOAT": DataType.FLOAT,
        "DOUBLE": DataType.FLOAT,
        "DECIMAL": DataType.FLOAT,
        "NUMERIC": DataType.FLOAT,
        "BOOLEAN": DataType.BOOLEAN,
        "BOOL": DataType.BOOLEAN,
        "STRING": DataType.STRING,
        "TEXT": DataType.STRING,
        "VARCHAR": DataType.STRING,
        "ANYURI": DataType.STRING,
    }
    return mapping.get(raw, DataType.UNKNOWN)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Semantic Bridge API",
        description="Swiss I14Y interoperability platform with semantic schema matching",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(search.router, tags=["search"])
    app.include_router(match.router, tags=["matching"])
    app.include_router(transform.router, tags=["transformation"])
    app.include_router(validate.router, tags=["validation"])
    app.include_router(shacl_match.router, tags=["shacl-matching"])
    app.include_router(compare.router, tags=["compare"])
    app.include_router(harmonize.router, tags=["harmonize"])

    return app


app = create_app()
