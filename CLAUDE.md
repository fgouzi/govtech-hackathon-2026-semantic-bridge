# semantic-bridge — AI Interoperability Platform

## What this project does

Local-first Python 3.12 platform that connects to the Swiss I14Y MCP server
(`https://mcp.i14y.d.c.bfs.admin.ch/mcp`), performs semantic schema matching between
datasets, generates data transformation plans, and validates interoperability.
No Docker. Runs entirely on localhost.

## Quick start

```bash
uv sync --extra dev
cp .env.example .env          # add INFOMANIAK_API_KEY + INFOMANIAK_PRODUCT_ID
uv run python scripts/seed_mock_concepts.py
uv run semantic-bridge serve  # starts FastAPI:8000 + Streamlit:8501 + Mock MCP:8002
```

Open http://localhost:8501 (Streamlit UI) or http://localhost:8000/docs (FastAPI).

> **Windows note:** if you see `ModuleNotFoundError: No module named 'typing_extensions'` after `uv sync`, run:
> ```bash
> uv run pip download typing_extensions --dest .te_pkg
> python -c "import zipfile; zipfile.ZipFile('.te_pkg/typing_extensions-4.15.0-py3-none-any.whl').extract('typing_extensions.py', '.venv/Lib/site-packages/')"
> ```

## Architecture in one line

```
CLI (Typer) → launches → FastAPI (:8000) + Streamlit (:8501) + Mock MCP (:8002)
                               ↓ async
                         Services (matching, transformation, validation)
                               ↓
                    MCP Client → I14Y live server (or mock fallback :8002)
                    LiteLLM   → Infomaniak AI (swiss-ai/Apertus-70B, via OpenAI-compatible API)
```

## Key directories

| Directory | Responsibility |
|---|---|
| `adapters/mcp/` | MCP client — httpx + SSE + JSON-RPC 2.0 + session ID management |
| `adapters/mock_mcp/` | Local mock I14Y MCP server (port 8002, FastAPI) |
| `adapters/cache.py` | SQLite TTL cache for MCP responses |
| `services/` | matching, transformation, validation, embedding |
| `agents/` | LiteLLM AI orchestration (Infomaniak Apertus primary, Claude fallback) |
| `domain/` | Pure Pydantic v2 models — no framework dependencies |
| `api/` | FastAPI routers + `dependencies.py` (Depends providers) |
| `ui/` | Streamlit multi-page app — calls FastAPI via httpx |
| `cli/` | Typer CLI entry point |
| `core/` | Config (pydantic-settings), logging (structlog), exceptions |
| `data/` | Sample CSVs (swiss/ + enterprise/) and SQLite DBs |
| `scripts/` | One-shot seed utilities |
| `tests/` | pytest + pytest-asyncio — 40 tests |

## MCP protocol — critical details

The I14Y server uses **MCP Streamable HTTP (protocol version 2024-11-05)**:

1. `POST /mcp` with `initialize` payload → server returns `mcp-session-id` in **response headers**
2. All subsequent POSTs **must** include `mcp-session-id: <token>` header
3. Responses are SSE (`text/event-stream`) — parse `data: {...}` lines
4. `notifications/initialized` is a fire-and-forget best-effort POST

The `MCPClient` in `adapters/mcp/client.py` handles this transparently:
- `_handshake()` calls `MCPTransport.post_initialize()` which returns `(body, response_headers)`
- Session ID stored in `self._session_ids[url]`
- All `call_tool()` and `list_tools()` calls pass `session_id=self._session_id`
- On I14Y failure → automatic fallback to local mock on port 8002

**Never** call the I14Y server with raw httpx — always go through `MCPClient`.

## I14Y MCP — available tools (34 total)

The live server exposes 34 tools. Most useful for matching:

| Tool | Use |
|---|---|
| `list_concepts` | Paginated list of all 604+ concepts |
| `list_concept_candidates_for_mapping` | Best candidates for a field |
| `full_text_search_resources` | Cross-resource full-text search |
| `get_concept` / `get_concept_by_identifier` | Detail for one concept |
| `list_datasets` / `get_dataset_structure` | Dataset schemas from I14Y catalog |
| `list_mappingtables` / `get_mappingtable_relations` | Existing BFS mappings |
| `get_codelist_entries` | All values in a codelist (cantons, etc.) |

## I14Y concept response structure

`list_concepts` response shape:
```json
{
  "pagination": {"total_rows": 604, "has_more": true},
  "data": {
    "data": [   ← unwrap with _extract_items() in app/main.py
      {
        "id": "uuid",
        "identifier": "2.16.756...",
        "name": {"de": "...", "fr": "...", "en": "..."},
        "description": {"de": "..."},
        "conceptType": "CodeList",
        "codeListEntryValueType": "String"
      }
    ]
  }
}
```

Helpers in `app/main.py`: `_extract_items()`, `_i14y_raw_to_concept()`, `_i14y_multilang()`.

## Streamlit page_link — important

Paths in `st.page_link()` are **relative to the `ui/` directory** (the entrypoint):
```python
st.page_link("main.py", label="Home")           # correct
st.page_link("pages/1_upload.py", label="...")  # correct
# NOT "ui/main.py" or "ui/pages/..." — those crash with StreamlitPageNotFoundError
```

## LLM routing (via LiteLLM)

```
INFOMANIAK_API_KEY set? → swiss-ai/Apertus-70B-Instruct-2509  (hébergé en Suisse, via Infomaniak)
otherwise               → claude-sonnet-4-6  (ANTHROPIC_API_KEY requis)
```

## Search — 3 entry points

```bash
# CLI (requires FastAPI running)
uv run semantic-bridge search "gemeinde bevoelkerung"
uv run semantic-bridge search "person name" --type concept
uv run semantic-bridge search "BFS communes" --type dataset --limit 5

# API
curl "http://localhost:8000/search?q=gemeinde&resource_type=dataset"

# UI
# http://localhost:8501 → page "Explore I14Y"
# search bar + type filter (all / dataset / concept / dataservice)
```

Route: `api/routes/search.py` → `full_text_search_resources` or `list_concept_candidates_for_mapping`.

## Running individual components

```bash
uv run pytest tests/ -v                                           # 40 tests
uv run uvicorn app.main:app --port 8000 --reload                  # FastAPI only
uv run streamlit run ui/main.py --server.port 8501                # Streamlit only
uv run uvicorn adapters.mock_mcp.server:app --port 8002           # Mock MCP only
uv run semantic-bridge match data/swiss/communes.csv -o out/m.json
uv run ruff check . && uv run mypy .
```

## Environment variables (see .env.example)

| Variable | Default | Description |
|---|---|---|
| `INFOMANIAK_API_KEY` | — | Clé API Infomaniak (scope : ai) — LLM principal |
| `INFOMANIAK_PRODUCT_ID` | — | ID produit AI Tools Infomaniak |
| `INFOMANIAK_MODEL` | `swiss-ai/Apertus-70B-Instruct-2509` | Modèle Infomaniak |
| `ANTHROPIC_API_KEY` | — | Claude API key (fallback si Infomaniak non configuré) |
| `I14Y_MCP_URL` | `https://mcp.i14y.d.c.bfs.admin.ch/mcp` | Swiss MCP server |
| `MOCK_MCP_URL` | `http://localhost:8002/mcp` | Local fallback |
| `FASTAPI_PORT` | `8000` | |
| `STREAMLIT_PORT` | `8501` | |
| `LOG_LEVEL` | `INFO` | |
| `CACHE_DB_PATH` | `data/cache.db` | SQLite MCP response cache |
| `FAISS_INDEX_PATH` | `data/faiss.index` | FAISS vector index (rebuilt if missing) |
| `MOCK_DB_PATH` | `data/mock.db` | Mock MCP concept database |

## Demo scenarios

1. **Swiss government** — `data/swiss/communes.csv` ↔ `data/swiss/population.csv`
2. **Enterprise HR ↔ CRM** — `data/enterprise/hr_employees.csv` ↔ `data/enterprise/crm_contacts.csv`

See `docs/use-cases.md` for step-by-step demo script.

## Known issues / workarounds

| Issue | Workaround |
|---|---|
| `typing_extensions` missing on Windows (uv) | See Quick Start note above |
| Streamlit `StreamlitPageNotFoundError` on `st.page_link` | Use paths relative to `ui/`, not project root |
| FAISS index stale after concept reload | Delete `data/faiss.index` — auto-rebuilt on startup |
| Mock MCP not seeded | Run `uv run python scripts/seed_mock_concepts.py` |

## Implementation status

- [x] Project scaffold + pyproject.toml (Python 3.12, uv)
- [x] Core layer (config, logging, exceptions)
- [x] Domain models (DatasetSchema, I14YConcept, MappingPlan, TransformationPlan)
- [x] MCP client — Streamable HTTP with session ID capture + mock fallback
- [x] Mock MCP server (26 Swiss I14Y concepts pre-loaded)
- [x] SQLite TTL cache
- [x] Embedding service (sentence-transformers/all-MiniLM-L6-v2 + FAISS)
- [x] Semantic matching (cosine 0.6 + lexical 0.3 + type heuristic 0.1)
- [x] Mapping + transformation + validation services
- [x] AI agent (LiteLLM — Infomaniak Apertus primary, Claude fallback)
- [x] FastAPI backend (POST /match /transform /validate, GET /health)
- [x] CLI (Typer — serve / match / transform / validate)
- [x] Streamlit UI (6 pages — upload/explore/matching/review/transform/validation)
- [x] Sample datasets (Swiss communes + population, enterprise HR + CRM)
- [x] 40 tests passing
- [x] Live I14Y connection verified (34 tools, 604+ concepts, session-based auth)
