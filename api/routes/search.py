"""Dataset and concept search via I14Y MCP."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from adapters.mcp.client import MCPClient
from api.dependencies import get_mcp_client

router = APIRouter()


@router.get("/dataset/{dataset_id}/structure")
async def get_dataset_structure(
    dataset_id: str,
    client: Annotated[MCPClient, Depends(get_mcp_client)],
) -> dict[str, Any]:
    """Fetch a dataset's structural schema from I14Y and return as DatasetSchema."""
    from domain.schema import DataType, DatasetSchema, SchemaField  # noqa: PLC0415

    # Resolve human-readable identifier (e.g. "36398596@org") to internal UUID
    uuid = await _resolve_dataset_uuid(dataset_id, client)

    try:
        result = await client.call_tool("get_dataset_structure", {"dataset_id": uuid})
        text = result.text()
        if not text:
            raise ValueError("empty response")
        data = json.loads(text)
    except Exception:
        try:
            result = await client.call_tool("get_dataset", {"dataset_id": uuid})
            text = result.text()
            data = json.loads(text) if text else {}
        except Exception as exc:
            return {"error": str(exc), "dataset_id": dataset_id}

    # Extract fields from various I14Y structure response shapes
    fields: list[SchemaField] = []
    raw_fields = _extract_structure_fields(data)

    for f in raw_fields:
        fname = _multilang(f.get("name") or f.get("label") or f.get("identifier") or "")
        raw_type = (f.get("dataType") or f.get("type") or f.get("xsdType") or "").upper()
        dtype = {
            "STRING": DataType.STRING, "VARCHAR": DataType.STRING, "TEXT": DataType.STRING,
            "INTEGER": DataType.INTEGER, "INT": DataType.INTEGER, "LONG": DataType.INTEGER,
            "FLOAT": DataType.FLOAT, "DOUBLE": DataType.FLOAT, "DECIMAL": DataType.FLOAT,
            "DATE": DataType.DATE, "DATETIME": DataType.DATE,
            "BOOLEAN": DataType.BOOLEAN,
        }.get(raw_type, DataType.UNKNOWN)
        if fname:
            fields.append(SchemaField(name=fname, data_type=dtype))

    # Build dataset title for schema name
    title_raw = data.get("title") or data.get("name") or {}
    title = _multilang(title_raw) or dataset_id[:8]
    identifier = data.get("identifier") or dataset_id

    schema = DatasetSchema(name=identifier, fields=fields, row_count=0)
    return {
        "schema": schema.model_dump(),
        "title": title,
        "identifier": identifier,
        "field_count": len(fields),
        "raw_structure": data,
    }


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


async def _resolve_dataset_uuid(identifier: str, client: MCPClient) -> str:
    """Return the internal UUID for a dataset identifier.

    If `identifier` is already a UUID it is returned unchanged.
    Otherwise, a full-text search is performed and the result whose `identifier`
    field matches exactly is used.
    """
    if _UUID_RE.match(identifier):
        return identifier
    try:
        result = await client.call_tool(
            "full_text_search_resources",
            {"query": identifier, "page": 1, "pageSize": 10},
        )
        data = json.loads(result.text()) if result.text() else {}
        inner = data.get("data", {})
        items: list[dict[str, Any]] = inner.get("data", []) if isinstance(inner, dict) else []
        # Prefer an exact identifier match; fall back to first dataset result
        for item in items:
            if item.get("identifier") == identifier:
                return item.get("id") or identifier
        for item in items:
            if (item.get("type") or "").lower() == "dataset":
                return item.get("id") or identifier
    except Exception:
        pass
    return identifier


_SHACL_NS = "http://www.w3.org/ns/shacl#"
_XSD_NS = "http://www.w3.org/2001/XMLSchema#"

_XSD_TYPE_MAP = {
    "integer": "INTEGER",
    "int": "INTEGER",
    "decimal": "DECIMAL",
    "double": "DOUBLE",
    "float": "FLOAT",
    "string": "STRING",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "dateTime": "DATETIME",
}


def _parse_shacl_jsonld(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse SHACL JSON-LD PropertyShape array into flat field dicts."""
    fields: list[dict[str, Any]] = []
    for item in items:
        types = item.get("@type", [])
        if f"{_SHACL_NS}PropertyShape" not in types:
            continue
        name_entries = item.get(f"{_SHACL_NS}name", [])
        name = next(
            (e.get("@value", "") for e in name_entries if isinstance(e, dict)),
            "",
        )
        dtype_entries = item.get(f"{_SHACL_NS}datatype", [])
        dtype_uri = next(
            (e.get("@id", "") for e in dtype_entries if isinstance(e, dict)),
            "",
        )
        xsd_local = dtype_uri.removeprefix(_XSD_NS)
        dtype = _XSD_TYPE_MAP.get(xsd_local, "STRING")
        order_entries = item.get(f"{_SHACL_NS}order", [])
        order = int(next(
            (e.get("@value", 0) for e in order_entries if isinstance(e, dict)),
            0,
        ))
        if name:
            fields.append({"name": name, "dataType": dtype, "order": order})
    return sorted(fields, key=lambda f: f["order"])


def _extract_structure_fields(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract field definitions from various I14Y dataset structure response shapes."""
    # SHACL JSON-LD array (actual I14Y get_dataset_structure response)
    raw_list = data.get("data")
    if isinstance(raw_list, list) and raw_list:
        shacl = _parse_shacl_jsonld(raw_list)
        if shacl:
            return shacl

    # Flat fields/attributes list
    for key in ("fields", "attributes", "variables", "columns", "items"):
        val = data.get(key)
        if isinstance(val, list) and val:
            return val  # type: ignore[return-value]

    # Nested data.data
    inner = data.get("data", {})
    if isinstance(inner, dict):
        for key in ("fields", "attributes", "variables", "columns", "items"):
            val = inner.get(key)
            if isinstance(val, list) and val:
                return val  # type: ignore[return-value]
        inner2 = inner.get("data", [])
        if isinstance(inner2, list):
            return inner2  # type: ignore[return-value]
    return []


class DatasetResult(BaseModel):
    id: str
    identifier: str
    title: str
    description: str
    resource_type: str
    publisher: str = ""


class SearchResponse(BaseModel):
    query: str
    total: int
    resource_type: str
    results: list[dict[str, Any]]


@router.get("/search")
async def search(
    q: Annotated[str, Query(description="Search query")],
    client: Annotated[MCPClient, Depends(get_mcp_client)],
    resource_type: Annotated[
        Literal["all", "dataset", "concept", "dataservice"],
        Query(description="Filter by resource type"),
    ] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SearchResponse:
    if resource_type == "concept":
        return await _search_concepts(q, page, page_size, client)
    return await _search_full_text(q, resource_type, page, page_size, client)


async def _search_full_text(
    query: str,
    resource_type: str,
    page: int,
    page_size: int,
    client: MCPClient,
) -> SearchResponse:
    try:
        result = await client.call_tool(
            "full_text_search_resources",
            {"query": query, "page": page, "pageSize": page_size},
        )
        data = json.loads(result.text()) if result.text() else {}
    except Exception:
        data = {}

    pagination = data.get("pagination", {})
    total = pagination.get("total_rows", 0)

    raw_items: list[dict[str, Any]] = []
    inner = data.get("data", {})
    if isinstance(inner, dict):
        raw_items = inner.get("data", [])
    elif isinstance(inner, list):
        raw_items = inner

    # Filter by type if requested
    if resource_type != "all":
        raw_items = [
            r for r in raw_items
            if (r.get("type") or r.get("resourceType") or "").lower() == resource_type.lower()
        ]

    results = [_normalize_result(r) for r in raw_items]
    return SearchResponse(query=query, total=total, resource_type=resource_type, results=results)


async def _search_concepts(
    query: str,
    page: int,
    page_size: int,
    client: MCPClient,
) -> SearchResponse:
    try:
        result = await client.call_tool(
            "list_concept_candidates_for_mapping",
            {"query": query, "page": page, "pageSize": page_size},
        )
        data = json.loads(result.text()) if result.text() else {}
    except Exception:
        # Fallback to full-text search
        return await _search_full_text(query, "concept", page, page_size, client)

    pagination = data.get("pagination", {})
    total = pagination.get("total_rows", 0)
    inner = data.get("data", {})
    raw_items: list[dict[str, Any]] = inner.get("data", []) if isinstance(inner, dict) else (inner if isinstance(inner, list) else [])

    results = [_normalize_result(r) for r in raw_items]
    return SearchResponse(query=query, total=total, resource_type="concept", results=results)


def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten an I14Y result to a consistent dict regardless of resource type."""
    title = raw.get("title") or raw.get("name") or {}
    description = raw.get("description") or raw.get("comment") or {}
    return {
        "id": raw.get("id", ""),
        "identifier": raw.get("identifier", ""),
        "title": _multilang(title),
        "description": _multilang(description)[:200],
        "type": raw.get("type") or raw.get("resourceType") or raw.get("conceptType") or "unknown",
        "publisher": _multilang(raw.get("publisher") or raw.get("creator") or ""),
        "raw": raw,
    }


def _multilang(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return (
            value.get("de") or value.get("fr") or value.get("it") or value.get("en")
            or next(iter(value.values()), "")
            or ""
        )
    return ""
