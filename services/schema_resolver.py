"""Schema resolution with OGD fallback via MCP get_distribution_content."""

from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd

from adapters.mcp.client import MCPClient
from core.exceptions import ClosedDatasetError
from core.logging import get_logger
from domain.schema import DataType, DatasetSchema, SchemaField

log = get_logger(__name__)

_XSD_TYPE_MAP = {
    "integer": DataType.INTEGER,
    "int": DataType.INTEGER,
    "long": DataType.INTEGER,
    "decimal": DataType.FLOAT,
    "double": DataType.FLOAT,
    "float": DataType.FLOAT,
    "string": DataType.STRING,
    "varchar": DataType.STRING,
    "text": DataType.STRING,
    "boolean": DataType.BOOLEAN,
    "date": DataType.DATE,
    "datetime": DataType.DATE,
}

_SHACL_NS = "http://www.w3.org/ns/shacl#"
_XSD_NS = "http://www.w3.org/2001/XMLSchema#"


class SchemaResolver:
    """Resolve an I14Y dataset identifier to a DatasetSchema.

    Resolution order:
    1. get_dataset_structure MCP call — if fields present, done.
    2. Fetch dataset metadata → find a public distribution URL.
    3. get_distribution_content MCP call → infer schema from CSV/JSON content.
    4. If no public distribution → raise ClosedDatasetError.
    """

    def __init__(self, mcp_client: MCPClient) -> None:
        self._mcp = mcp_client
        # Cache to avoid double-fetching content when harmonize reuses resolver results
        self._content_cache: dict[str, bytes] = {}

    async def resolve(
        self, dataset_id: str
    ) -> tuple[DatasetSchema, str, str | None]:
        """Return (schema, title, download_url | None).

        download_url is set when the schema was inferred from distribution content,
        so the harmonize endpoint can reuse it without a second MCP call.

        Raises ClosedDatasetError if the dataset is not publicly accessible.
        """
        # Step 1 — Try structured schema from MCP
        schema, title, structure_data = await self._fetch_structure(dataset_id)
        if schema and schema.fields:
            log.info("schema_resolved_from_structure", dataset_id=dataset_id, fields=len(schema.fields))
            return schema, title, None

        # Step 2 — Fetch dataset metadata to find distribution URL
        dataset_meta = await self._fetch_dataset_meta(dataset_id)
        resolved_title = title or _multilang(dataset_meta.get("title") or dataset_meta.get("name") or {}) or dataset_id
        download_url = _find_public_distribution(dataset_meta)

        if not download_url:
            log.warning("dataset_no_public_distribution", dataset_id=dataset_id)
            raise ClosedDatasetError(
                dataset_id,
                reason="Dataset has no public distribution URL (may be restricted or unpublished)",
            )

        # Step 3 — Fetch content via MCP and infer schema
        content = await self._fetch_distribution_content(download_url)
        schema = _infer_schema_from_content(content, dataset_id)

        if not schema.fields:
            raise ClosedDatasetError(
                dataset_id,
                reason=f"Distribution content at {download_url!r} could not be parsed",
            )

        log.info(
            "schema_resolved_from_distribution",
            dataset_id=dataset_id,
            url=download_url,
            fields=len(schema.fields),
        )
        return schema, resolved_title, download_url

    async def get_cached_content(self, download_url: str) -> bytes:
        """Return distribution content (from cache if already fetched)."""
        if download_url not in self._content_cache:
            self._content_cache[download_url] = await self._fetch_distribution_content(download_url)
        return self._content_cache[download_url]

    async def _fetch_structure(
        self, dataset_id: str
    ) -> tuple[DatasetSchema | None, str, dict[str, Any]]:
        uuid = await self._resolve_uuid(dataset_id)
        try:
            result = await self._mcp.call_tool("get_dataset_structure", {"dataset_id": uuid})
            text = result.text() if result else ""
            if not text:
                return None, dataset_id, {}
            data = json.loads(text)
        except Exception as exc:
            log.debug("get_dataset_structure_failed", dataset_id=dataset_id, exc=str(exc))
            return None, dataset_id, {}

        # Extract title from response metadata
        title_raw = data.get("title") or data.get("name") or {}
        title = _multilang(title_raw) or dataset_id

        fields = _extract_fields(data)
        if not fields:
            return None, title, data

        schema = DatasetSchema(name=title or dataset_id, fields=fields, row_count=0)
        return schema, title, data

    async def _fetch_dataset_meta(self, dataset_id: str) -> dict[str, Any]:
        uuid = await self._resolve_uuid(dataset_id)
        for tool in ("get_dataset", "get_dataset_by_identifier"):
            try:
                arg_key = "dataset_id" if tool == "get_dataset" else "identifier"
                result = await self._mcp.call_tool(tool, {arg_key: uuid})
                text = result.text() if result else ""
                if text:
                    return json.loads(text)  # type: ignore[no-any-return]
            except Exception:
                continue
        return {}

    async def _fetch_distribution_content(self, url: str) -> bytes:
        if url in self._content_cache:
            return self._content_cache[url]
        try:
            result = await self._mcp.call_tool("get_distribution_content", {"url": url})
            text = result.text() if result else ""
            content = text.encode("utf-8") if isinstance(text, str) else (text or b"")
        except Exception as exc:
            log.warning("get_distribution_content_failed", url=url, exc=str(exc))
            # Try direct httpx as last resort (OGD data is public)
            import httpx  # noqa: PLC0415
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url, follow_redirects=True)
                r.raise_for_status()
                content = r.content
        self._content_cache[url] = content
        return content

    async def _resolve_uuid(self, identifier: str) -> str:
        """Return internal UUID if identifier is human-readable, else passthrough."""
        import re  # noqa: PLC0415
        _UUID_RE = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
        )
        if _UUID_RE.match(identifier):
            return identifier
        try:
            result = await self._mcp.call_tool(
                "full_text_search_resources",
                {"query": identifier, "page": 1, "pageSize": 10},
            )
            data = json.loads(result.text()) if result.text() else {}
            inner = data.get("data", {})
            items: list[dict[str, Any]] = inner.get("data", []) if isinstance(inner, dict) else []
            for item in items:
                if item.get("identifier") == identifier:
                    return item.get("id") or identifier
            for item in items:
                if (item.get("type") or "").lower() == "dataset":
                    return item.get("id") or identifier
        except Exception:
            pass
        return identifier


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _multilang(value: Any) -> str:
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


def _find_public_distribution(meta: dict[str, Any]) -> str | None:
    """Extract the first public download/access URL from dataset metadata."""
    # I14Y uses distributions[] array (DCAT-AP style)
    distributions: list[dict[str, Any]] = meta.get("distributions", []) or meta.get("distribution", []) or []

    # Also check nested data.distributions
    if not distributions:
        inner = meta.get("data", {})
        if isinstance(inner, dict):
            distributions = inner.get("distributions", []) or inner.get("distribution", []) or []

    for dist in distributions:
        for key in ("downloadUrl", "download_url", "accessUrl", "access_url", "url"):
            url = dist.get(key)
            if isinstance(url, str) and url.startswith("http"):
                return url
        # Handle list values
        for key in ("downloadUrl", "download_url", "accessUrl", "access_url"):
            val = dist.get(key)
            if isinstance(val, list) and val:
                u = val[0]
                if isinstance(u, str) and u.startswith("http"):
                    return u
    return None


def _infer_schema_from_content(content: bytes, name_hint: str) -> DatasetSchema:
    """Infer a DatasetSchema from raw CSV or JSON bytes."""
    text = content.decode("utf-8", errors="replace")

    # Try CSV
    try:
        df = pd.read_csv(io.StringIO(text), nrows=100, on_bad_lines="skip", sep=None, engine="python")
        if len(df.columns) >= 1:
            return DatasetSchema.from_dataframe(df, name=name_hint)
    except Exception:
        pass

    # Try JSON (list of objects)
    try:
        data = json.loads(text)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            df = pd.json_normalize(data[:100])
            return DatasetSchema.from_dataframe(df, name=name_hint)
        if isinstance(data, dict):
            # Try common wrappers: data[], results[], records[]
            for key in ("data", "results", "records", "items", "features"):
                inner = data.get(key)
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    df = pd.json_normalize(inner[:100])
                    return DatasetSchema.from_dataframe(df, name=name_hint)
    except Exception:
        pass

    return DatasetSchema(name=name_hint, fields=[], row_count=0)


def _extract_fields(data: dict[str, Any]) -> list[SchemaField]:
    """Extract fields from I14Y structure response (supports SHACL JSON-LD and flat formats)."""
    # SHACL JSON-LD list
    raw_list = data.get("data")
    if isinstance(raw_list, list) and raw_list:
        shacl = _parse_shacl_jsonld(raw_list)
        if shacl:
            return shacl

    # Flat fields/attributes list
    for key in ("fields", "attributes", "variables", "columns", "items"):
        val = data.get(key)
        if isinstance(val, list) and val:
            return _parse_flat_fields(val)

    # Nested data.data
    inner = data.get("data", {})
    if isinstance(inner, dict):
        for key in ("fields", "attributes", "variables", "columns"):
            val = inner.get(key)
            if isinstance(val, list) and val:
                return _parse_flat_fields(val)
    return []


def _parse_shacl_jsonld(items: list[dict[str, Any]]) -> list[SchemaField]:
    fields: list[SchemaField] = []
    parsed: list[tuple[int, SchemaField]] = []
    for item in items:
        types = item.get("@type", [])
        if f"{_SHACL_NS}PropertyShape" not in types:
            continue
        name_entries = item.get(f"{_SHACL_NS}name", [])
        name = next((e.get("@value", "") for e in name_entries if isinstance(e, dict)), "")
        dtype_entries = item.get(f"{_SHACL_NS}datatype", [])
        dtype_uri = next((e.get("@id", "") for e in dtype_entries if isinstance(e, dict)), "")
        xsd_local = dtype_uri.removeprefix(_XSD_NS).lower()
        dtype = _XSD_TYPE_MAP.get(xsd_local, DataType.UNKNOWN)
        order_entries = item.get(f"{_SHACL_NS}order", [])
        order = int(next((e.get("@value", 0) for e in order_entries if isinstance(e, dict)), 0))
        if name:
            parsed.append((order, SchemaField(name=name, data_type=dtype)))
    parsed.sort(key=lambda x: x[0])
    fields = [f for _, f in parsed]
    return fields


def _parse_flat_fields(items: list[dict[str, Any]]) -> list[SchemaField]:
    fields: list[SchemaField] = []
    for f in items:
        fname = _multilang(f.get("name") or f.get("label") or f.get("identifier") or "")
        raw_type = (f.get("dataType") or f.get("type") or f.get("xsdType") or "").lower()
        dtype = _XSD_TYPE_MAP.get(raw_type, DataType.UNKNOWN)
        if fname:
            fields.append(SchemaField(name=fname, data_type=dtype))
    return fields
