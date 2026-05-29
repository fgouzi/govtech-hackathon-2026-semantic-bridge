"""
Register native Open WebUI tools that call the semantic-bridge FastAPI.
These bypass the MCP protocol and give the LLM direct access to I14Y search.
"""
import sqlite3
import json
import time
import glob
import sys
from pathlib import Path

# Find DB
patterns = [
    r"C:\Users\*\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db",
    str(Path.home() / ".local/share/open-webui/webui.db"),
]
DB = None
for pat in patterns:
    matches = glob.glob(pat)
    if matches:
        DB = matches[0]
        break

if not DB:
    print("[WARN] Open WebUI DB not found — skipping tool registration")
    sys.exit(0)
TARGET_MODEL = "i14y-discovery-swiss-ai-apertus-70b-instruct-2509"
FASTAPI_BASE = "http://localhost:8000"

# Get admin user id
conn = sqlite3.connect(DB)
user_row = conn.execute("SELECT id FROM user WHERE name = 'User' LIMIT 1").fetchone()
user_id = user_row[0] if user_row else "admin"

# ─── Tool 1: Full-text search across I14Y resources ──────────────────────────
SEARCH_TOOL_ID = "i14y_search"
SEARCH_TOOL_CONTENT = '''"""
title: Recherche I14Y
description: Recherche des datasets, concepts et dataservices sur la plateforme I14Y (interoperabilite suisse). Appelle cet outil pour toute question sur des donnees ouvertes suisses.
author: semantic-bridge
version: 1.0.0
"""

import httpx


class Tools:
    FASTAPI_BASE = "http://localhost:8000"

    def search_i14y(
        self,
        query: str,
        resource_type: str = "all",
        page_size: int = 10,
    ) -> str:
        """
        Recherche des ressources sur la plateforme I14Y (datasets, concepts, dataservices suisses).
        Appelle cet outil EN PREMIER pour toute question sur des donnees suisses.
        Pour de meilleurs resultats, fais deux appels: un en francais, un en allemand.

        :param query: Requete de recherche en francais ou en allemand (ex: "communes population", "Bevoelkerung Gemeinde")
        :param resource_type: Type de ressource: "all", "dataset", "concept", "dataservice". Defaut: "all"
        :param page_size: Nombre de resultats (5-20). Defaut: 10
        :return: Liste JSON des ressources I14Y trouvees avec id, titre, description, type
        """
        try:
            r = httpx.get(
                f"{self.FASTAPI_BASE}/search",
                params={"q": query, "resource_type": resource_type, "page_size": page_size},
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if not results:
                    return f"Aucun resultat trouve pour: {query!r} (type={resource_type})"
                lines = [f"Resultats I14Y pour '{query}' ({len(results)} trouvés):"]
                for item in results:
                    title = item.get("title", item.get("identifier", "?"))
                    desc = item.get("description", "")[:120]
                    rtype = item.get("type", "?")
                    rid = item.get("identifier") or item.get("id", "")
                    lines.append(f"- [{rtype}] {title} (ID: {rid}): {desc}")
                return "\\n".join(lines)
            return f"Erreur API I14Y: HTTP {r.status_code}"
        except Exception as e:
            return f"Erreur de connexion a I14Y: {e}"

    def get_concept_details(self, concept_id: str) -> str:
        """
        Obtient les details complets d\'un concept I14Y (description, type de donnees, valeurs possibles).

        :param concept_id: Identifiant du concept I14Y (UUID ou OID comme 2.16.756...)
        :return: Details JSON du concept
        """
        try:
            r = httpx.get(
                f"{self.FASTAPI_BASE}/concepts/{concept_id}",
                timeout=15,
            )
            if r.status_code == 200:
                c = r.json()
                return json.dumps(c, ensure_ascii=False, indent=2)
            # Try search as fallback
            r2 = httpx.get(
                f"{self.FASTAPI_BASE}/search",
                params={"q": concept_id, "resource_type": "concept", "page_size": 3},
                timeout=15,
            )
            if r2.status_code == 200:
                return r2.text
            return f"Concept {concept_id!r} non trouve"
        except Exception as e:
            return f"Erreur: {e}"
'''

SEARCH_TOOL_SPECS = json.dumps([
    {
        "name": "search_i14y",
        "description": "Recherche des ressources sur la plateforme I14Y (datasets, concepts, dataservices suisses). Appelle cet outil EN PREMIER pour toute question sur des donnees suisses.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Requete de recherche en francais ou en allemand"
                },
                "resource_type": {
                    "type": "string",
                    "enum": ["all", "dataset", "concept", "dataservice"],
                    "description": "Type de ressource a chercher. Defaut: all"
                },
                "page_size": {
                    "type": "integer",
                    "description": "Nombre de resultats (5-20). Defaut: 10"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_concept_details",
        "description": "Obtient les details complets d'un concept I14Y par son identifiant",
        "parameters": {
            "type": "object",
            "properties": {
                "concept_id": {
                    "type": "string",
                    "description": "Identifiant du concept I14Y (UUID ou OID)"
                }
            },
            "required": ["concept_id"]
        }
    }
])

SEARCH_TOOL_META = json.dumps({
    "description": "Recherche I14Y — datasets et concepts de la plateforme nationale d'interoperabilite suisse",
    "manifest": {"title": "Recherche I14Y", "author": "semantic-bridge", "version": "1.0.0"}
})

now = int(time.time())

# Insert or replace
conn.execute(
    """INSERT OR REPLACE INTO tool (id, user_id, name, content, specs, meta, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (SEARCH_TOOL_ID, user_id, "Recherche I14Y", SEARCH_TOOL_CONTENT,
     SEARCH_TOOL_SPECS, SEARCH_TOOL_META, now, now)
)
conn.commit()
print(f"[OK] Tool '{SEARCH_TOOL_ID}' enregistre dans Open WebUI")

# Enable this tool on the Apertus model
model_row = conn.execute(
    "SELECT params, meta FROM model WHERE id = ?", (TARGET_MODEL,)
).fetchone()
if model_row:
    m_params = json.loads(model_row[0]) if model_row[0] else {}
    m_meta = json.loads(model_row[1]) if model_row[1] else {}

    # Set tool_ids so the model always has I14Y search available
    m_params["tool_ids"] = [SEARCH_TOOL_ID]

    # Ensure tool calling is enabled
    m_meta["capabilities"] = {
        "vision": False,
        "usage": True,
        "citations": False,
        "tools": True,
    }

    conn.execute(
        "UPDATE model SET params = ?, meta = ? WHERE id = ?",
        (json.dumps(m_params), json.dumps(m_meta), TARGET_MODEL)
    )
    conn.commit()
    print(f"[OK] Tool '{SEARCH_TOOL_ID}' assigne au modele {TARGET_MODEL!r}")
else:
    print(f"[WARN] Modele {TARGET_MODEL!r} non trouve — tool non assigne")

# ─── Update system prompt from file ──────────────────────────────────────────
SYSTEM_PROMPT_FILE = Path(__file__).parent / "system_prompt_i14y.txt"
if SYSTEM_PROMPT_FILE.exists():
    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    model_row2 = conn.execute(
        "SELECT params FROM model WHERE id = ?", (TARGET_MODEL,)
    ).fetchone()
    if model_row2:
        p = json.loads(model_row2[0]) if model_row2[0] else {}
        p["system"] = system_prompt
        p["tool_ids"] = [SEARCH_TOOL_ID]
        conn.execute(
            "UPDATE model SET params = ? WHERE id = ?",
            (json.dumps(p), TARGET_MODEL)
        )
        conn.commit()
        print(f"[OK] System prompt mis a jour depuis {SYSTEM_PROMPT_FILE.name}")

# ─── Pre-enable tool for all users ────────────────────────────────────────────
users = conn.execute("SELECT id FROM user").fetchall()
for (uid,) in users:
    row = conn.execute("SELECT settings FROM user WHERE id = ?", (uid,)).fetchone()
    settings = json.loads(row[0]) if row[0] else {}
    if "ui" not in settings:
        settings["ui"] = {}
    settings["ui"]["toolIds"] = [SEARCH_TOOL_ID]
    settings["ui"]["selectedToolIds"] = [SEARCH_TOOL_ID]
    settings["ui"]["showTools"] = True
    conn.execute("UPDATE user SET settings = ? WHERE id = ?", (json.dumps(settings), uid))
conn.commit()
print(f"[OK] Tool pre-active pour {len(users)} utilisateur(s)")

conn.close()
print("\nRedemarrer Open WebUI pour activer les outils.")
