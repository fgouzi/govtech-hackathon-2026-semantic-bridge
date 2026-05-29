import asyncio
import httpx
import json

DATASETS = {
    "BUILDING_DWELLING_MASTER_DATA": "3ecde98c-f38e-445e-829a-ed34e2c4a2f1",
    "BUILDING_MASTER_DATA": "88b9b0cb-3e9e-435e-9845-6cca56763874",
    "DWELLING_MASTER_DATA": "87753b45-49f4-40f8-b479-e32124b1b6ad",
    "Logements niveaux geographiques (36162945)": "ae78f338-6ac4-482a-a9de-99dd5361fce2",
    "Logements canton pieces surface (36162950)": "f0b144b1-edf7-4632-a32d-897b1ffe7d45",
    "Batiments categorie (35367678)": "4fb43c3c-a200-418f-9eee-8400019313ab",
    "Batiments categorie (36503047)": "abe395d5-943e-4adc-8ded-24b32e798ded",
}


def multilang(obj, langs=("fr", "de", "en")):
    if isinstance(obj, dict):
        for lang in langs:
            if obj.get(lang):
                return obj[lang]
    return str(obj) if obj else ""


async def main():
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        results = {}
        for name, uuid in DATASETS.items():
            url = f"https://api.i14y.admin.ch/api/public/v1/datasets/{uuid}"
            r = await client.get(url)
            data = r.json()
            ds = data.get("data", {})
            title = multilang(ds.get("title", {}))
            desc = multilang(ds.get("description", {}))
            distrib = ds.get("distributions", [])
            keywords_raw = ds.get("keywords", [])
            keywords = []
            for k in keywords_raw:
                kw = multilang(k) if isinstance(k, dict) else str(k)
                keywords.append(kw)
            themes = ds.get("themes", [])

            print(f"=== {name} ===")
            print(f"  UUID: {uuid}")
            print(f"  Title: {title}")
            print(f"  Description: {desc[:300]}")
            print(f"  Keywords: {keywords[:8]}")
            print(f"  Themes: {[multilang(t) for t in themes[:3]]}")
            print(f"  Distributions ({len(distrib)}):")
            for d in distrib[:4]:
                fmt = d.get("format", {})
                fmt_code = fmt.get("code", "") if isinstance(fmt, dict) else str(fmt)
                d_title = multilang(d.get("title", {}))
                d_url = d.get("downloadURL") or d.get("accessURL") or ""
                print(f"    - [{fmt_code}] {d_title} | {d_url}")
            print()
            results[name] = {
                "uuid": uuid,
                "title": title,
                "desc": desc,
                "keywords": keywords,
                "distributions": distrib,
            }

        # Now: analyze which datasets can be linked
        print("\n" + "=" * 60)
        print("ANALYSE DES LIAISONS POSSIBLES")
        print("=" * 60)

        # Check dataset-specific concept usage via MCP
        from adapters.mcp.client import MCPClient
        from adapters.cache import SQLiteCache
        from core.config import get_settings

        settings = get_settings()
        cache = SQLiteCache(settings.cache_db_path)
        async with MCPClient(str(settings.i14y_mcp_url), str(settings.mock_mcp_url), cache) as mcp:
            # Get concepts related to buildings and dwellings
            for concept_id in ["EGID", "EWID", "GKAT", "GAREA", "WAREA", "WHGNR", "DEINR"]:
                r = await mcp.call_tool("get_concept_by_identifier", {"identifier": concept_id})
                text = r.text()
                try:
                    cdata = json.loads(text)
                    c = cdata.get("data", cdata)
                    cname = multilang(c.get("name", {}))
                    cdesc = multilang(c.get("description", {}))
                    print(f"Concept [{concept_id}]: {cname}")
                    print(f"  -> {cdesc[:200]}")
                except Exception:
                    print(f"Concept [{concept_id}]: (not found)")
                print()


asyncio.run(main())
