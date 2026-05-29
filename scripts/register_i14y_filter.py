"""
Register an Open WebUI Filter Function that automatically injects I14Y search results
into every chat message — no user toggle required.

Filter Functions run server-side on every message (inlet hook).
Type "filter" + is_global=1 + is_active=1 = always-on, no UI interaction needed.
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
    print("[WARN] Open WebUI DB not found — skipping filter registration")
    sys.exit(0)

conn = sqlite3.connect(DB)

# Get admin user id
user_row = conn.execute("SELECT id FROM user LIMIT 1").fetchone()
user_id = user_row[0] if user_row else "admin"

FILTER_ID = "i14y_auto_search"
FILTER_CONTENT = '''"""
title: I14Y Auto-Search Filter
description: Recherche automatiquement des datasets I14Y pertinents avant chaque reponse. Aucune action utilisateur requise.
author: semantic-bridge
version: 1.1.0
"""

import httpx
from typing import Optional


class Filter:
    """
    Open WebUI Filter — runs automatically on every message (no toggle needed).
    Searches I14Y in FR + DE and injects results as context before the LLM replies.
    """

    FASTAPI_BASE = "http://localhost:8000"

    def _search(self, query: str, page_size: int = 12) -> list[dict]:
        try:
            r = httpx.get(
                f"{self.FASTAPI_BASE}/search",
                params={"q": query, "resource_type": "all", "page_size": page_size},
                timeout=20,
            )
            if r.status_code == 200:
                return r.json().get("results", [])
        except Exception:
            pass
        return []

    def _translate_to_de(self, text: str) -> str:
        """Simple FR→DE keyword mapping for common Swiss data topics."""
        translations = {
            "sante": "Gesundheit", "santé": "Gesundheit", "hopital": "Krankenhaus",
            "population": "Bevölkerung", "habitants": "Einwohner",
            "immobilier": "Immobilien", "batiment": "Gebäude", "logement": "Wohnen",
            "commune": "Gemeinde", "communes": "Gemeinden", "canton": "Kanton",
            "transport": "Verkehr", "mobilite": "Mobilität", "mobilité": "Mobilität",
            "education": "Bildung", "école": "Schule", "formation": "Ausbildung",
            "emploi": "Beschäftigung", "travail": "Arbeit", "chomage": "Arbeitslosigkeit",
            "environnement": "Umwelt", "energie": "Energie", "énergie": "Energie",
            "finance": "Finanzen", "budget": "Budget", "impot": "Steuer",
            "agriculture": "Landwirtschaft", "foret": "Wald", "forêt": "Wald",
            "entreprise": "Unternehmen", "commerce": "Handel",
            "personne": "Person", "age": "Alter", "naissance": "Geburt",
            "deces": "Tod", "décès": "Tod", "mortalite": "Sterblichkeit",
            "accident": "Unfall", "crime": "Kriminalität", "securite": "Sicherheit",
            "tourisme": "Tourismus", "culture": "Kultur", "sport": "Sport",
            "medecin": "Arzt", "medicament": "Medikament", "maladie": "Krankheit",
        }
        de_terms = []
        for word in text.lower().split():
            word_clean = word.strip(".,;:!?")
            if word_clean in translations:
                de_terms.append(translations[word_clean])
        return " ".join(de_terms) if de_terms else text  # fallback: same query

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """Inject I14Y search results before the LLM sees the message."""
        messages = body.get("messages", [])
        if not messages:
            return body

        # Get the last user message text
        last_user_msg = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            None,
        )
        if not last_user_msg or len(last_user_msg.strip()) < 3:
            return body

        query_fr = last_user_msg.strip()[:200]  # cap length
        query_de = self._translate_to_de(query_fr)

        # Search in FR and DE, deduplicate by identifier
        seen_ids: set[str] = set()
        all_results: list[dict] = []

        for q in [query_fr, query_de]:
            for item in self._search(q, page_size=12):
                rid = item.get("identifier") or item.get("id", "")
                if rid and rid not in seen_ids:
                    seen_ids.add(rid)
                    all_results.append(item)

        if not all_results:
            return body  # nothing found — pass through unchanged

        # Format as context block
        lines = [
            f"=== RESSOURCES I14Y TROUVÉES ({len(all_results)} résultats) ===",
            f"Requêtes: [{query_fr}] + [{query_de}]",
            "",
        ]
        for item in all_results[:20]:
            title = item.get("title") or item.get("identifier") or "?"
            desc = (item.get("description") or "")[:120]
            rtype = item.get("type", "?")
            rid = item.get("identifier") or item.get("id", "")
            pub = item.get("publisher", "")
            lines.append(f"• [{rtype}] {title}")
            lines.append(f"  ID: {rid} | Éditeur: {pub}")
            if desc:
                lines.append(f"  {desc}")
            lines.append("")

        lines.append("=== FIN RÉSULTATS I14Y ===")
        i14y_block = "\\n".join(lines)

        # Inject as context into existing system message, or create one
        for msg in messages:
            if msg.get("role") == "system":
                msg["content"] = i14y_block + "\\n\\n" + msg["content"]
                return body

        # No system message — prepend one
        body["messages"] = [{"role": "system", "content": i14y_block}] + messages
        return body
'''

FILTER_META = json.dumps({
    "description": "Recherche automatique I14Y — injecte les datasets/concepts pertinents avant chaque réponse. Aucun toggle utilisateur requis.",
    "manifest": {
        "title": "I14Y Auto-Search Filter",
        "author": "semantic-bridge",
        "version": "1.1.0",
        "license": "MIT",
    },
})

now = int(time.time())

conn.execute(
    """INSERT OR REPLACE INTO function
       (id, user_id, name, type, content, meta, is_active, is_global, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        FILTER_ID,
        user_id,
        "I14Y Auto-Search",
        "filter",
        FILTER_CONTENT,
        FILTER_META,
        1,   # is_active = True
        1,   # is_global = True → runs on all models, all chats
        now,
        now,
    ),
)
conn.commit()
print(f"[OK] Filter '{FILTER_ID}' enregistré (type=filter, is_global=1, is_active=1)")

# Assign filter to the I14Y model specifically too (belt + suspenders)
TARGET_MODEL = "i14y-discovery-swiss-ai-apertus-70b-instruct-2509"
row = conn.execute("SELECT meta FROM model WHERE id = ?", (TARGET_MODEL,)).fetchone()
if row:
    meta = json.loads(row[0]) if row[0] else {}
    info = meta.get("info", {})
    if "filter_ids" not in info:
        info["filter_ids"] = []
    if FILTER_ID not in info["filter_ids"]:
        info["filter_ids"].append(FILTER_ID)
    meta["info"] = info
    conn.execute("UPDATE model SET meta = ? WHERE id = ?", (json.dumps(meta), TARGET_MODEL))
    conn.commit()
    print(f"[OK] Filter assigné au modèle {TARGET_MODEL!r}")

conn.close()
print("\n[INFO] Redémarrer Open WebUI pour activer le filter.")
print("[INFO] La recherche I14Y sera maintenant automatique sur chaque message.")
