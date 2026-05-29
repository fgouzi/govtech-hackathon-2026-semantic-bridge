"""Find I14Y concepts for dataset 'Wohneigentumsquote nach Kanton'."""
import asyncio
import json

from adapters.cache import SQLiteCache
from adapters.mcp.client import MCPClient
from core.config import get_settings

DATASET_ID = "36398596@bundesamt-fur-statistik-bfs"

# Attributes expected in "Wohneigentumsquote nach Kanton" (BFS):
# - Kanton (canton abbreviation / BFS number)
# - Jahr (reference year)
# - Wohneigentumsquote (home ownership rate, %)
# - Possibly: Eigentuemertyp (owner type: natural/legal person)
ATTR_KEYWORDS = [
    "kanton", "jahr", "wohn", "eigentum", "quote", "region",
    "gemeinde", "gebaeude", "wohnung", "immobil", "prozent", "anteil",
]


async def main() -> None:
    settings = get_settings()
    cache = SQLiteCache(settings.cache_db_path)
    await cache.initialize()
    client = MCPClient(
        primary_url=settings.i14y_mcp_url,
        fallback_url=settings.mock_mcp_url,
        cache=cache,
    )
    async with client._transport:
        await client.connect()

        # 1. Paginate all 604 concepts (page-based, 25/page = 25 pages)
        print("Paginating 604 I14Y concepts...")
        all_concepts = []
        for page in range(1, 26):
            result = await client.call_tool("list_concepts", {"limit": 25, "page": page})
            text = result.text()
            try:
                data = json.loads(text)
                inner = data.get("data", {}).get("data", [])
                if not inner:
                    break
                all_concepts.extend(inner)
            except Exception as e:
                print(f"  page {page} ERR: {e}")
                break

        print(f"Fetched {len(all_concepts)} concepts total")

        # 2. Filter by keyword relevance
        matched = []
        for it in all_concepts:
            name = it.get("name", {})
            label = (name.get("de") or name.get("en") or name.get("fr") or "").lower()
            desc = it.get("description", {})
            desc_text = (desc.get("de", "") if isinstance(desc, dict) else str(desc)).lower()
            ident = (it.get("identifier", "") or "").lower()
            combined = f"{label} {desc_text} {ident}"
            score = sum(1 for kw in ATTR_KEYWORDS if kw in combined)
            if score > 0:
                matched.append((score, it))

        matched.sort(key=lambda x: -x[0])

        print(f"\n{'='*60}")
        print(f"Relevant concepts ({len(matched)} found)")
        print(f"{'='*60}")
        for score, it in matched[:20]:
            name = it.get("name", {})
            label = name.get("de") or name.get("en") or name.get("fr") or str(name)
            desc = it.get("description", {})
            desc_de = (desc.get("de", "") if isinstance(desc, dict) else str(desc))[:120]
            ctype = it.get("conceptType", "")
            ident = it.get("identifier", it.get("id", ""))
            print(f"\n  [{ctype}] {label}  (score={score})")
            print(f"    identifier: {ident}")
            if desc_de:
                print(f"    desc: {desc_de}")

        # 3. Get details for the specific Wohneigentumsquote dataset
        print(f"\n{'='*60}")
        print("Dataset details from full_text_search")
        print(f"{'='*60}")
        result = await client.call_tool(
            "full_text_search_resources",
            {"query": "Wohneigentumsquote", "limit": 10}
        )
        text = result.text()
        try:
            data = json.loads(text)
            items = data
            for _ in range(3):
                if isinstance(items, dict) and "data" in items:
                    items = items["data"]
            for it in (items if isinstance(items, list) else []):
                ident = it.get("identifier", "")
                if "36398596" in ident or "wohneig" in str(it).lower():
                    print(json.dumps(it, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"ERR: {e}\nRAW: {text[:800]}")

        # 4. Try get_concept for known BFS identifiers
        print(f"\n{'='*60}")
        print("Specific concept lookups (BFS known identifiers)")
        print(f"{'='*60}")
        known_ids = ["CH_KTNR", "KTNR", "KANTONSNUM", "Jahr", "YEAR"]
        for cid in known_ids:
            result = await client.call_tool("get_concept_by_identifier", {"identifier": cid})
            text = result.text()
            if text and not text.startswith("Error"):
                try:
                    data = json.loads(text)
                    print(f"\n  {cid}:", json.dumps(data, ensure_ascii=False)[:300])
                except Exception:
                    pass


asyncio.run(main())
