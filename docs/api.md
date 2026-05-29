# API Reference

Base URL: `http://localhost:8000`

Interactive docs: http://localhost:8000/docs (Swagger UI)

---

## GET /search

Search I14Y datasets, concepts and data services.

**Parameters:**
- `q` (string, required) — search query
- `resource_type` (string, default `"all"`) — `all` | `dataset` | `concept` | `dataservice`
- `page` (int, default 1)
- `page_size` (int, default 10, max 50)

**Examples:**
```bash
curl "http://localhost:8000/search?q=gemeinde+bevoelkerung&resource_type=dataset"
curl "http://localhost:8000/search?q=person+name&resource_type=concept"
```

**Response:**
```json
{
  "query": "gemeinde bevoelkerung",
  "total": 646,
  "resource_type": "all",
  "results": [
    {
      "id": "uuid",
      "identifier": "lustat-szbv-lu",
      "title": "Szenarien zur Bevölkerungsentwicklung der Luzerner Gemeinden",
      "description": "...",
      "type": "Dataset",
      "publisher": "Kanton Luzern"
    }
  ]
}
```

Internally routes to `full_text_search_resources` (type=all/dataset/dataservice)
or `list_concept_candidates_for_mapping` (type=concept) on the I14Y MCP server.

---

## GET /health

Returns platform health and MCP connection status.

**Response 200:**
```json
{
  "status": "ok",
  "mcp_connected": true,
  "mcp_url": "https://mcp.i14y.d.c.bfs.admin.ch/mcp",
  "mcp_mode": "live",
  "version": "0.1.0"
}
```

`mcp_mode` is `"live"` when connected to I14Y, `"mock"` when using local fallback.

---

## POST /match

Match a dataset schema against I14Y concepts.

**Request body:**
```json
{
  "schema": {
    "name": "communes",
    "fields": [
      {"name": "bfs_nr", "data_type": "INTEGER", "sample_values": ["1", "2", "3"]},
      {"name": "gemeinde_name", "data_type": "STRING", "sample_values": ["Zürich", "Bern"]}
    ],
    "row_count": 20
  },
  "use_ai": true
}
```

`use_ai`: if `true`, low-confidence matches (<0.7) are enriched via LLM.

**Response 200:**
```json
{
  "source_schema": {"name": "communes", "fields": [...], "row_count": 20},
  "mappings": [
    {
      "source_field": "bfs_nr",
      "matched_concept": {
        "id": "ch.bfs.gemeinde.bfs_nr",
        "name": "BFS.MunicipalityNumber",
        "description": "Official BFS municipality number",
        "data_type": "INTEGER",
        "uri": "https://ld.admin.ch/property/bfsNumber"
      },
      "confidence": 0.92,
      "method": "embedding+lexical",
      "explanation": null
    },
    {
      "source_field": "gemeinde_name",
      "matched_concept": {
        "id": "ch.bfs.gemeinde.name",
        "name": "Address.Municipality",
        "description": "Name of Swiss municipality",
        "data_type": "STRING",
        "uri": "https://ld.admin.ch/property/municipalityName"
      },
      "confidence": 0.88,
      "method": "embedding+lexical",
      "explanation": null
    }
  ],
  "overall_confidence": 0.90
}
```

---

## POST /transform

Apply a transformation plan to records.

**Request body:**
```json
{
  "mapping": { ... },
  "records": [
    {"bfs_nr": "351", "gemeinde_name": "Zürich", "kanton_kuerzel": "ZH"}
  ]
}
```

**Response 200:**
```json
{
  "transformed": [
    {"BFS.MunicipalityNumber": "351", "Address.Municipality": "Zürich"}
  ],
  "plan": {
    "rules": [
      {"operation": "rename", "source_field": "bfs_nr", "target_field": "BFS.MunicipalityNumber"},
      {"operation": "rename", "source_field": "gemeinde_name", "target_field": "Address.Municipality"}
    ],
    "source_schema": {...},
    "target_schema": null
  }
}
```

---

## POST /validate

Validate a mapping plan for errors and warnings.

**Request body:**
```json
{
  "mapping": { ... }
}
```

**Response 200:**
```json
{
  "passed": true,
  "errors": [],
  "warnings": [
    {
      "field": "plz",
      "issue": "low_confidence",
      "detail": "Confidence 0.58 below threshold 0.7",
      "severity": "warning"
    }
  ],
  "summary": "1 warning, 0 errors"
}
```

**Error codes:**

| Code | Meaning |
|---|---|
| `missing_mapping` | Field has no matched concept |
| `low_confidence` | Confidence < 0.7 |
| `type_mismatch` | Source and concept data types incompatible |
| `duplicate_target` | Two fields mapped to same concept |

---

## MCP Tool Exposure (port 8002)

The platform also exposes its own MCP tools via the mock MCP server:

| Tool | Description |
|---|---|
| `match_dataset_schema` | Match a DatasetSchema against I14Y concepts |
| `generate_mapping` | Generate MappingPlan between two schemas |
| `validate_mapping` | Validate a MappingPlan |
| `transform_record` | Apply transformation plan to a single record |
