# 🔗 Semantic Bridge

**Swiss I14Y Interoperability Platform** — local-first semantic schema matching, powered by AI.

Connects to the [Swiss I14Y MCP server](https://www.i14y.admin.ch/), performs semantic matching between datasets, generates transformation plans, and validates interoperability. No Docker. Runs entirely on localhost.

---

## Quick Start

### 1. Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh
# or on Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Install dependencies

```bash
cd c:\dev\hack2026
uv sync --extra dev
```

> **Windows note:** uv on Windows may omit `typing_extensions.py` from the venv on first sync. If you see `ModuleNotFoundError: No module named 'typing_extensions'`, run:
> ```bash
> uv run pip download typing_extensions --dest .te_pkg
> python -c "import zipfile; zipfile.ZipFile('.te_pkg/typing_extensions-4.15.0-py3-none-any.whl').extract('typing_extensions.py', '.venv/Lib/site-packages/')"
> del /s .te_pkg
> ```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:
```
INFOMANIAK_API_KEY=...     # API key Infomaniak (scope : ai)
INFOMANIAK_PRODUCT_ID=...  # ID produit AI Tools
# Optional fallback:
# ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Seed mock I14Y data

```bash
uv run python scripts/seed_mock_concepts.py
```

### 5. Launch everything

```bash
uv run semantic-bridge serve
```

Opens:
- **Streamlit UI** → http://localhost:8501
- **FastAPI docs** → http://localhost:8000/docs
- **Health check** → http://localhost:8000/health

---

## Demo Scenarios

### Scenario A — Swiss Government Data

1. Upload `data/swiss/communes.csv`
2. Click "Run Semantic Matching"
3. See `bfs_nr` → `BFS.MunicipalityNumber` (92%), `gemeinde_name` → `Address.Municipality` (88%)
4. Review and validate → proceed to transform preview

### Scenario B — Enterprise HR ↔ CRM

1. Upload `data/enterprise/hr_employees.csv`
2. Match → `full_name` → `Person.FullName`, `birth_date` → `Person.DateOfBirth`
3. Upload `data/enterprise/crm_contacts.csv` and repeat
4. Compare the two mapping plans — shared concepts = join keys

---

## CLI Usage

```bash
# Match a CSV schema
uv run semantic-bridge match data/swiss/communes.csv --output out/mapping.json

# Apply transformation
uv run semantic-bridge transform out/mapping.json data/swiss/communes.csv --output out/transformed.json

# Validate a mapping
uv run semantic-bridge validate out/mapping.json
```

---

## Architecture

```
CLI (Typer) → FastAPI (:8000) → Services → MCP Client → I14Y server
                    ↓
         Streamlit UI (:8501)
```

See [docs/architecture.md](docs/architecture.md) for the full diagram.

---

## Project Structure

| Directory | Contents |
|---|---|
| `adapters/mcp/` | MCP client — httpx + SSE + JSON-RPC 2.0 |
| `adapters/mock_mcp/` | Local mock I14Y MCP server (port 8002) |
| `services/` | Matching, transformation, validation, embeddings |
| `agents/` | LiteLLM AI orchestration (Infomaniak Apertus primary, Claude fallback) |
| `domain/` | Pydantic v2 domain models |
| `api/` | FastAPI routers |
| `ui/` | Streamlit multi-page app |
| `cli/` | Typer CLI |
| `data/` | Sample CSV datasets |
| `tests/` | pytest test suite |

---

## Running Tests

```bash
uv run pytest tests/ -v
```

---

## Linting & Type Checking

```bash
uv run ruff check .
uv run mypy .
```

---

## MCP Integration

The platform connects to `https://mcp.i14y.d.c.bfs.admin.ch/mcp` using the Model Context Protocol (JSON-RPC 2.0 over HTTP/SSE). If the server is unreachable, it automatically falls back to a local mock MCP server with pre-loaded Swiss I14Y concepts.

See [docs/adr/001-mcp-client-design.md](docs/adr/001-mcp-client-design.md) for the design rationale.

---

## Contributing

This is a hackathon project. Clean architecture, no Docker, Python 3.12 throughout.
