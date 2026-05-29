# Copilot Instructions — semantic-bridge

## Project overview

Local-first Python 3.12 interoperability platform. Connects to the Swiss I14Y MCP server,
performs semantic schema matching between CSV datasets, generates transformation plans,
and validates interoperability. No Docker. Single-command launch.

**Entry points:**
- `uv run semantic-bridge serve` — starts everything
- `uv run uvicorn app.main:app --port 8000 --reload` — FastAPI only
- `uv run streamlit run ui/main.py --server.port 8501` — Streamlit only

## Stack

| Layer | Technology |
|---|---|
| Package manager | `uv` (not pip, not poetry) |
| Runtime | Python 3.12 pinned via `.python-version` |
| API | FastAPI + uvicorn |
| UI | Streamlit multi-page (`ui/pages/`) |
| CLI | Typer (`cli/main.py`) |
| Models | Pydantic v2 (`BaseModel`, `computed_field`) |
| Config | `pydantic-settings` via `core/config.py` → `get_settings()` |
| Logging | structlog via `core/logging.py` → `get_logger(__name__)` |
| HTTP | httpx async + httpx-sse |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 + FAISS |
| LLM | LiteLLM → swiss-ai/Apertus-70B-Instruct-2509 via Infomaniak (primary) or claude-sonnet-4-6 (fallback) |
| DB | aiosqlite (SQLite — no ORM) |
| Tests | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |

## Architecture layers (strict dependency direction)

```
cli/ → app/ → api/ → services/ → domain/
                ↓
          adapters/mcp/     adapters/cache.py
          adapters/mock_mcp/
                ↓
          agents/           (LiteLLM, imports services)
```

`domain/` has **no** framework imports — pure Pydantic v2 only.
`services/` imports `domain/` only.
`adapters/` imports `core/` and `domain/` only.
`api/` uses FastAPI `Depends()` from `api/dependencies.py` — never instantiate services directly in routes.

## MCP protocol — critical details

The I14Y server (`https://mcp.i14y.d.c.bfs.admin.ch/mcp`) uses **MCP Streamable HTTP 2024-11-05**:

1. POST `initialize` → server returns `mcp-session-id` in **response headers**
2. All subsequent POSTs must include `mcp-session-id: <token>` header
3. Responses come as SSE (`text/event-stream`) with `data: {...}` lines
4. Notifications (`notifications/initialized`) are best-effort POST, no response expected

**Never** call the I14Y server without a session ID — it returns HTTP 400 "Missing session ID".

The `MCPClient` handles this automatically:
- `_handshake()` → `MCPTransport.post_initialize()` → captures session from headers
- `call_tool()` / `list_tools()` → `MCPTransport.post_message(..., session_id=self._session_id)`
- On connection failure → transparent fallback to mock MCP on port 8002

## I14Y MCP — available tools (34 total)

Key tools for interoperability matching:

| Tool | Args | Use for |
|---|---|---|
| `list_concepts` | `page`, `pageSize` | Load all 604+ I14Y concepts (paginated) |
| `get_concept` | `concept_id` | Full detail for one concept |
| `get_concept_by_identifier` | `identifier` | Lookup by OID or short name |
| `list_concept_candidates_for_mapping` | `query` | **Best for field matching** |
| `full_text_search_resources` | `query` | Cross-resource full-text search |
| `list_datasets` | `page`, `pageSize` | I14Y dataset catalog |
| `get_dataset_structure` | `dataset_id` | Schema/structure of a dataset |
| `list_mappingtables` | — | Existing mapping tables |
| `get_mappingtable_relations` | `mappingtable_id` | Value-level mapping relations |
| `get_codelist_entries` | `concept_id` | All values in a codelist |

## I14Y concept response structure

`list_concepts` returns:
```json
{
  "pagination": {"page": 1, "total_rows": 604, "has_more": true},
  "data": {
    "data": [                          ← actual concepts array
      {
        "id": "uuid",                  ← use as I14YConcept.id
        "identifier": "OID or short",  ← human-readable ID, use as uri
        "name": {"de": "...", "fr": "...", "en": "..."},  ← multilingual
        "description": {"de": "...", "fr": "...", "en": "..."},
        "conceptType": "CodeList" | "DataElement",
        "codeListEntryValueType": "String" | "Integer" | "Date"  ← maps to DataType
      }
    ]
  }
}
```

Helper functions in `app/main.py`:
- `_extract_items(data)` — unwraps `data.data.data` nesting
- `_i14y_raw_to_concept(raw)` — maps I14Y fields to `I14YConcept`
- `_i14y_multilang(value)` — extracts DE/FR/IT/EN from multilingual dicts

## Domain models — key types

```python
# domain/schema.py
class DataType(str, Enum): STRING, INTEGER, FLOAT, DATE, BOOLEAN, UNKNOWN
class SchemaField(BaseModel): name, data_type, sample_values, nullable
class DatasetSchema(BaseModel): name, fields, row_count
    @classmethod def from_dataframe(df, name) → DatasetSchema

# domain/concept.py
class I14YConcept(BaseModel): id, name, description, data_type, uri, category, aliases

# domain/mapping.py
class FieldMapping(BaseModel): source_field, matched_concept, confidence, method, explanation
class MappingPlan(BaseModel): source_schema, mappings
    @computed_field overall_confidence → float

# domain/transformation.py
class TransformationRule(BaseModel): operation (rename|cast|concat|split|normalize), source_field, target_field, params
class TransformationPlan(BaseModel): rules, source_schema, target_schema
class ValidationReport(BaseModel): passed, errors, warnings
```

## FastAPI patterns

Always use `Depends()` from `api/dependencies.py`:
```python
from api.dependencies import get_matching_service, get_concepts
@router.post("/my-endpoint")
async def my_route(
    matching: Annotated[SemanticMatchingService, Depends(get_matching_service)],
    concepts: Annotated[list[I14YConcept], Depends(get_concepts)],
) -> MyResponse: ...
```

App state is set in `app/main.py` lifespan:
`request.app.state.mcp_client`, `.embedding_service`, `.concepts`, `.cache`

## Streamlit patterns

- All pages are in `ui/pages/` and are auto-discovered by Streamlit
- Pages call FastAPI via `httpx.Client` (sync) — FastAPI is always the source of truth
- Session state keys: `uploaded_schema`, `uploaded_df`, `mapping_plan`, `validation_report`, `api_url`
- `st.page_link()` paths are **relative to `ui/`** (not project root):
  - Home: `"main.py"` ✓ (not `"ui/main.py"` ✗)
  - Page: `"pages/1_upload.py"` ✓ (not `"ui/pages/1_upload.py"` ✗)

## Search — 3 entry points

| Entry point | How |
|---|---|
| **Streamlit UI** | Page "Explore I14Y" → search bar + type filter (all/dataset/concept/dataservice) |
| **CLI** | `uv run semantic-bridge search "query" --type dataset` |
| **API** | `GET /search?q=query&resource_type=dataset&page_size=10` |

All three call the same `GET /search` FastAPI endpoint (`api/routes/search.py`),
which routes to `full_text_search_resources` or `list_concept_candidates_for_mapping` on I14Y.

`_normalize_result(raw)` in `api/routes/search.py` flattens any I14Y resource type to:
`{id, identifier, title, description, type, publisher, raw}`.

## Matching score formula

```python
score = 0.60 × cosine_similarity(field_embedding, concept_embedding)  # FAISS
      + 0.30 × rapidfuzz.token_sort_ratio(field_name, concept_name) / 100
      + 0.10 × type_compatibility_score  # 1.0 if compatible, 0.3 if not
```
Threshold: ≥ 0.70 → accepted | 0.50–0.70 → warning | < 0.50 → error

## Testing conventions

```bash
uv run pytest tests/ -v          # all tests (40 total)
uv run pytest tests/test_X.py    # single file
```

- Fixtures in `tests/conftest.py`: `sample_concepts`, `sample_schema`, `sample_mapping_plan`
- No integration tests against live I14Y (use mock fixtures)
- `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`
- Mock `EmbeddingService` with `unittest.mock.MagicMock(spec=EmbeddingService)`

## Common pitfalls

| Pitfall | Fix |
|---|---|
| `st.page_link("ui/main.py")` | Use `"main.py"` (relative to `ui/`) |
| Calling I14Y without session ID | Always go through `MCPClient` — never raw httpx |
| `typing_extensions` missing on Windows | See README Quick Start note |
| `uv run pytest` not found | Use `uv sync --extra dev` first |
| FAISS index stale after concept change | Delete `data/faiss.index` — rebuilt on next start |
| Adding emojis to print/logs on Windows | Windows CP1252 can't encode — use ASCII or reconfigure stdout |

## File naming rules

- New FastAPI routes → `api/routes/<name>.py`, register in `app/main.py`
- New Streamlit pages → `ui/pages/<N>_<name>.py` (N = next integer)
- New domain models → `domain/<name>.py`
- New services → `services/<name>.py`, inject via `api/dependencies.py`
