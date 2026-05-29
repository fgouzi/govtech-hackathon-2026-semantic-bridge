"""Local mock MCP server — mirrors I14Y API for offline/fallback use."""

import json
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock I14Y MCP Server", version="0.1.0")

_DB_PATH = Path("data/mock.db")

_TOOLS = [
    {
        "name": "search_concepts",
        "description": "Search I14Y interoperability concepts by keyword",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_concept",
        "description": "Get a specific I14Y concept by ID",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "list_datasets",
        "description": "List available datasets in the I14Y catalog",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "match_dataset_schema",
        "description": "Match a dataset schema against I14Y concepts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "schema": {"type": "object", "description": "DatasetSchema JSON"},
                "use_ai": {"type": "boolean", "default": True},
            },
            "required": ["schema"],
        },
    },
    {
        "name": "generate_mapping",
        "description": "Generate a mapping plan between two schemas",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_schema": {"type": "object"},
                "target_schema": {"type": "object"},
            },
            "required": ["source_schema", "target_schema"],
        },
    },
    {
        "name": "validate_mapping",
        "description": "Validate a mapping plan",
        "inputSchema": {
            "type": "object",
            "properties": {"mapping": {"type": "object"}},
            "required": ["mapping"],
        },
    },
    {
        "name": "transform_record",
        "description": "Apply transformation plan to a single record",
        "inputSchema": {
            "type": "object",
            "properties": {
                "record": {"type": "object"},
                "plan": {"type": "object"},
            },
            "required": ["record", "plan"],
        },
    },
]


async def _get_db() -> aiosqlite.Connection:
    return await aiosqlite.connect(_DB_PATH)


@app.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _error_response(None, -32700, "Parse error")

    method = body.get("method", "")
    req_id = body.get("id")
    params = body.get("params", {}) or {}

    if method == "initialize":
        return _result_response(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "mock-i14y-mcp", "version": "0.1.0"},
            },
        )

    if method == "notifications/initialized":
        return JSONResponse(content={}, status_code=204)

    if method == "tools/list":
        return _result_response(req_id, {"tools": _TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments: dict[str, Any] = params.get("arguments", {})
        result = await _dispatch_tool(tool_name, arguments)
        return _result_response(req_id, result)

    return _error_response(req_id, -32601, f"Method not found: {method}")


async def _dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    db = await _get_db()
    try:
        if name == "search_concepts":
            return await _search_concepts(db, args.get("query", ""))
        if name == "get_concept":
            return await _get_concept(db, args.get("id", ""))
        if name == "list_datasets":
            return await _list_datasets(db)
        # For platform tools, return a simple acknowledgment
        return _text_result(f"Tool '{name}' dispatched. Use FastAPI /match, /transform, /validate.")
    finally:
        await db.close()


async def _search_concepts(db: aiosqlite.Connection, query: str) -> dict[str, Any]:
    query_lower = f"%{query.lower()}%"
    async with db.execute(
        """
        SELECT id, name, description, data_type, uri, category, aliases
        FROM concepts
        WHERE lower(name) LIKE ? OR lower(description) LIKE ? OR lower(aliases) LIKE ?
        LIMIT 10
        """,
        (query_lower, query_lower, query_lower),
    ) as cursor:
        rows = await cursor.fetchall()

    concepts = [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "data_type": r[3],
            "uri": r[4],
            "category": r[5],
            "aliases": json.loads(r[6]) if r[6] else [],
        }
        for r in rows
    ]
    return _text_result(json.dumps({"concepts": concepts}))


async def _get_concept(db: aiosqlite.Connection, concept_id: str) -> dict[str, Any]:
    async with db.execute(
        "SELECT id, name, description, data_type, uri, category, aliases FROM concepts WHERE id = ?",
        (concept_id,),
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        return _text_result(json.dumps({"error": f"Concept {concept_id!r} not found"}))

    return _text_result(
        json.dumps(
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "data_type": row[3],
                "uri": row[4],
                "category": row[5],
                "aliases": json.loads(row[6]) if row[6] else [],
            }
        )
    )


async def _list_datasets(db: aiosqlite.Connection) -> dict[str, Any]:
    datasets = [
        {"id": "ch.bfs.communes", "name": "BFS Commune Register", "description": "Swiss municipalities"},
        {"id": "ch.bfs.population", "name": "Population Statistics", "description": "Swiss population by commune"},
        {"id": "ch.bfs.enterprises", "name": "Business Register (BUR)", "description": "Swiss enterprise register"},
        {"id": "ch.admin.persons", "name": "Person Register", "description": "Person identity data"},
    ]
    return _text_result(json.dumps({"datasets": datasets}))


def _text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _result_response(req_id: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error_response(req_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})
