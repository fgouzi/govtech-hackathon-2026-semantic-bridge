# I14Y MCP Server — Tool Reference

Base URL: `https://mcp.i14y.d.c.bfs.admin.ch/mcp`
Protocol: MCP Streamable HTTP 2024-11-05
Tools: 34 available

**All calls require a valid session — use `MCPClient.call_tool()`, never raw httpx.**

---

## Concepts

### `list_concepts`
List all I14Y data concepts (paginated, 604+ total).

```python
result = await client.call_tool("list_concepts", {"page": 1, "pageSize": 25})
# Response: {"pagination": {...}, "data": {"data": [...]}}
# Use _extract_items(data) to get the list
```

### `get_concept`
Full detail for one concept by UUID.

```python
result = await client.call_tool("get_concept", {"concept_id": "uuid-string"})
```

### `get_concept_by_identifier`
Lookup by OID or short identifier (e.g. `"HGDE_KT"`).

```python
result = await client.call_tool("get_concept_by_identifier", {"identifier": "HGDE_KT"})
```

### `list_concept_candidates_for_mapping`
**Best tool for field matching** — returns ranked candidates for a field/schema/attribute.

```python
result = await client.call_tool("list_concept_candidates_for_mapping", {
    "query": "birth date of a person"
})
```

### `get_concept_codelist`
All codelist entries for a concept.

```python
result = await client.call_tool("get_concept_codelist", {"concept_id": "uuid"})
```

### `get_codelist_entries`
Codelist entries with full annotations.

```python
result = await client.call_tool("get_codelist_entries", {"concept_id": "uuid"})
```

### `get_codelist_entry_by_code`
Single codelist entry by code value.

```python
result = await client.call_tool("get_codelist_entry_by_code", {
    "concept_id": "uuid", "code": "ZH"
})
```

### `get_codelist_entries_children`
Child entries of a parent code in a hierarchical codelist.

```python
result = await client.call_tool("get_codelist_entries_children", {
    "concept_id": "uuid", "parent_code": "CH"
})
```

### `search_codelist_entries`
Search entries within a codelist by label or code.

```python
result = await client.call_tool("search_codelist_entries", {
    "concept_id": "uuid", "query": "Zürich"
})
```

---

## Datasets

### `list_datasets`
List datasets in the I14Y catalog.

```python
result = await client.call_tool("list_datasets", {"page": 1, "pageSize": 20})
```

### `get_dataset`
Full metadata for a dataset by UUID.

```python
result = await client.call_tool("get_dataset", {"dataset_id": "uuid"})
```

### `get_dataset_by_identifier`
Dataset by human-readable identifier.

```python
result = await client.call_tool("get_dataset_by_identifier", {"identifier": "BFS_AGVZ"})
```

### `get_dataset_structure`
Structural schema of a dataset (fields, types).

```python
result = await client.call_tool("get_dataset_structure", {"dataset_id": "uuid"})
```

### `check_dataset_has_structure`
Check if a dataset has a structural model defined.

```python
result = await client.call_tool("check_dataset_has_structure", {"dataset_id": "uuid"})
```

---

## Mapping Tables

### `list_mappingtables`
All mapping tables registered on I14Y.

```python
result = await client.call_tool("list_mappingtables", {})
```

### `get_mappingtable`
Metadata for a mapping table.

```python
result = await client.call_tool("get_mappingtable", {"mappingtable_id": "uuid"})
```

### `get_mappingtable_relations`
All value-level mapping relations for a mapping table.

```python
result = await client.call_tool("get_mappingtable_relations", {"mappingtable_id": "uuid"})
```

---

## Search

### `full_text_search_resources`
Full-text search across all I14Y resources (datasets, concepts, services, etc.).

```python
result = await client.call_tool("full_text_search_resources", {"query": "municipality population"})
# Response: {"pagination": {...}, "data": {"data": [...]}}
```

---

## Data Services

### `list_dataservices`
Data services (APIs) registered on I14Y.

```python
result = await client.call_tool("list_dataservices", {"page": 1})
```

### `get_dataservice` / `get_dataservice_by_identifier`
Detail for a specific data service.

---

## Public Services

### `list_publicservices` / `get_publicservice` / `get_publicservice_by_identifier`
Public services registered on I14Y (CPSV-AP).

### `get_publicservice_relations`
Services related to a given public service.

---

## Catalogs & Vocabularies

### `list_catalogs` / `get_catalog` / `get_catalog_records` / `get_catalog_themes`
DCAT-AP catalogs on I14Y.

### `list_vocabularies` / `get_vocabulary`
Controlled vocabularies.

### `list_agents` / `get_agent`
Publishing organisations registered on I14Y.

### `get_distribution_content`
Fetch content of a DCAT distribution file.

---

## Response pattern

All list tools return:
```json
{
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total_pages": 25,
    "total_rows": 604,
    "has_more": true,
    "next_page": 2
  },
  "pagination_instruction": "More pages available. Call again with page=2...",
  "data": {
    "data": [...]      ← actual items — use _extract_items() in app/main.py
  }
}
```

Multilingual text fields:
```json
{"de": "German text", "fr": "French text", "it": "Italian text", "en": "English text"}
```
Use `_i14y_multilang(value)` helper — prefers DE > FR > IT > EN.
