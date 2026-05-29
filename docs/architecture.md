# Architecture

## Layer diagram

```
┌───────────────────────────────────────────────────────────────┐
│  CLI (Typer)  ·  semantic-bridge serve/match/transform/validate│
└──────────────────────┬────────────────────────────────────────┘
                       │ subprocess.Popen
          ┌────────────┼──────────────────┐
          ▼            ▼                  ▼
   ┌─────────────┐ ┌──────────────┐ ┌─────────────┐
   │ Mock MCP    │ │  FastAPI     │ │  Streamlit  │
   │ :8002       │ │  :8000       │ │  :8501      │
   └─────────────┘ └──────┬───────┘ └──────┬──────┘
                          │                │ httpx POST
                          │ Depends()      └────────────►┐
                          ▼                              │
               ┌──────────────────────────────────────┐ │
               │           Services Layer             │◄┘
               │  SemanticMatchingService             │
               │  MappingGenerationService            │
               │  TransformationEngine                │
               │  ValidationEngine                    │
               │  EmbeddingService (FAISS)            │
               └───────────┬───────────────┬──────────┘
                           │               │
              ┌────────────┘               └────────────┐
              ▼                                         ▼
   ┌─────────────────────┐               ┌─────────────────────┐
   │  MCPClient          │               │  InteroperabilityAgent│
   │  adapters/mcp/      │               │  LiteLLM            │
   │                     │               │  → claude-sonnet-4-6│
   │  tries: I14Y (:443) │               │  → ollama/llama3    │
   │  fallback: mock     │               └─────────────────────┘
   │  (:8002)            │
   │  cache: SQLite TTL  │
   └─────────────────────┘
```

## MCP Streamable HTTP — session protocol

The I14Y server uses the MCP Streamable HTTP transport (2024-11-05), which is **stateful**.
Each connection requires a session token obtained at handshake.

```
Client                              I14Y Server
  │                                      │
  │── POST /mcp (initialize, no token) ──►│
  │◄─ 200 SSE + mcp-session-id: <token> ─│  ← capture this header
  │                                      │
  │── POST /mcp (notifications/init) ───►│  ← best-effort, session token in header
  │◄─ 204 (no body) ─────────────────────│
  │                                      │
  │── POST /mcp (tools/list) ────────────►│  ← mcp-session-id required
  │◄─ 200 SSE {"result": {"tools": [...]}}│
  │                                      │
  │── POST /mcp (tools/call) ────────────►│  ← mcp-session-id required
  │◄─ 200 SSE {"result": {"content": [...]}}│
```

**Without the session ID header** → HTTP 400 "Bad Request: Missing session ID".

### Client implementation (`adapters/mcp/client.py`)

```python
async def _handshake(self, url: str) -> None:
    body, resp_headers = await self._transport.post_initialize(url, req)
    session_id = resp_headers.get("mcp-session-id")
    if session_id:
        self._session_ids[url] = session_id   # stored per URL

async def call_tool(self, name, arguments):
    req = protocol.build_tool_call(name, arguments, next(_id_counter))
    raw = await self._transport.post_message(
        self._active_url, req,
        session_id=self._session_id   # injected into every request
    )
```

### Fallback logic

```python
async def connect(self) -> bool:
    try:
        await self._handshake(self._primary_url)   # I14Y live
        self._using_mock = False
        return True
    except MCPConnectionError:
        await self._handshake(self._fallback_url)  # local mock :8002
        self._using_mock = True
        return False
```

## I14Y concept response structure

`list_concepts` returns a **doubly-nested** structure:

```json
{
  "pagination": {"page": 1, "total_rows": 604, "has_more": true},
  "data": {
    "data": [        ← actual list is at data["data"]["data"]
      {
        "id": "uuid-string",
        "identifier": "2.16.756.5.30.1.127.3.10.1.1.4",
        "name": {"de": "...", "fr": "...", "en": "..."},
        "description": {"de": "...", "fr": "..."},
        "conceptType": "CodeList" | "DataElement",
        "codeListEntryValueType": "String" | "Integer" | "Date"
      }
    ]
  }
}
```

Helper in `app/main.py`:
- `_extract_items(data)` — unwraps any of: `data.data.data`, `data.data`, `data.items`, flat list
- `_i14y_raw_to_concept(raw)` — maps to `I14YConcept` domain model
- `_i14y_multilang(value)` — extracts DE > FR > IT > EN from multilingual dicts

## Data flow — Semantic Matching

```
CSV Upload
    │
    ▼
pandas infer dtypes → DatasetSchema (domain/schema.py)
    │
    ▼  POST /match
SemanticMatchingService.match_schema()
    │
    ├─► MCPClient.call_tool("list_concept_candidates_for_mapping", {query: field_name})
    │   OR call_tool("full_text_search_resources", {query: field_name})
    │       └─► I14Y live (34 tools, 604 concepts) or local mock (26 concepts)
    │           └─► list[I14YConcept]
    │
    ├─► EmbeddingService.encode(field_names + concept_names)
    │       └─► sentence-transformers/all-MiniLM-L6-v2
    │           └─► np.ndarray (L2-normalised) → FAISS IndexFlatIP
    │
    ├─► rapidfuzz.token_sort_ratio (lexical similarity)
    │
    ├─► datatype_heuristic(field.data_type, concept.data_type)
    │
    └─► score = 0.6×cosine + 0.3×lexical + 0.1×type
            │
            ├─ ≥ 0.70 → FieldMapping accepted
            ├─ 0.50–0.69 → accepted with warning
            └─ < 0.50 → InteroperabilityAgent (LLM disambiguation via LiteLLM)
    │
    ▼
MappingPlan(source_schema, mappings[], overall_confidence)
```

## Caching strategy

| Resource | Storage | TTL |
|---|---|---|
| MCP `tools/list` | SQLite `data/cache.db` | 1 hour |
| MCP `call_tool` results | SQLite `data/cache.db` | 1 hour |
| FAISS concept index | `data/faiss.index` | rebuilt on startup if missing |
| Session state | Streamlit `st.session_state` | browser session |

## Module dependency rules

```
domain/       ← no imports from this project
core/         ← stdlib + pydantic-settings only
adapters/     ← core/ + domain/ only
services/     ← domain/ + adapters/ (embedding)
agents/       ← domain/ + services/ + core/
api/          ← domain/ + services/ + agents/ + adapters/
app/          ← api/ + adapters/ + services/ + core/
cli/          ← app/ (subprocess) + domain/ (for schema inference)
ui/           ← calls FastAPI via httpx (no direct service imports)
```

## Key design decisions

- See [ADR 001](adr/001-mcp-client-design.md) — custom MCP client rationale
- Streamlit pages use `st.page_link("pages/X.py")` — paths relative to `ui/` entrypoint
- All async where possible; Streamlit pages use sync `httpx.Client` (Streamlit runs sync)
