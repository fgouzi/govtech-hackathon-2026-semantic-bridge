"""
Register Open WebUI tools for dataset comparison, schema inspection, and harmonization.
Adds: compare_datasets, get_dataset_schema, harmonize_datasets, export_mapping_table
"""
import glob
import json
import sqlite3
import sys
import time
from pathlib import Path

# Find Open WebUI DB
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
    print("[WARN] Open WebUI DB not found — skipping matching tools registration")
    sys.exit(0)

FASTAPI_BASE = "http://localhost:8000"
TARGET_MODEL = "i14y-discovery-swiss-ai-apertus-70b-instruct-2509"

conn = sqlite3.connect(DB)
user_row = conn.execute("SELECT id FROM user LIMIT 1").fetchone()
user_id = user_row[0] if user_row else "admin"

# ─── Tool: dataset_compare ────────────────────────────────────────────────────
COMPARE_TOOL_ID = "dataset_compare"
COMPARE_CONTENT = '''"""
title: Comparaison de Datasets I14Y
description: Compare deux datasets I14Y et retourne un score de compatibilite avec systeme de validation vert/orange/rouge et suggestions de table de mapping.
author: semantic-bridge
version: 1.0.0
"""

import httpx
import json


class Tools:
    FASTAPI_BASE = "http://localhost:8000"

    def compare_datasets(self, dataset_a_id: str, dataset_b_id: str) -> str:
        """
        Compare deux datasets I14Y et retourne leur compatibilite.
        Affiche un score, une lampe de validation (vert/orange/rouge), les cles de jointure et les suggestions de table de mapping.

        :param dataset_a_id: Identifiant I14Y du premier dataset (UUID ou identifiant court)
        :param dataset_b_id: Identifiant I14Y du deuxieme dataset (UUID ou identifiant court)
        :return: Rapport de comparaison en Markdown avec score et lampe de validation
        """
        try:
            r = httpx.post(
                f"{self.FASTAPI_BASE}/compare",
                json={"dataset_a_id": dataset_a_id, "dataset_b_id": dataset_b_id},
                timeout=60,
            )
            if r.status_code != 200:
                return f"Erreur API: HTTP {r.status_code} — {r.text[:200]}"

            data = r.json()
            lamp = data.get("lamp", "RED")
            score = data.get("overall_score", 0.0)
            title_a = data.get("dataset_a_title", dataset_a_id)
            title_b = data.get("dataset_b_title", dataset_b_id)
            join_candidates = data.get("join_candidates", [])
            mapping_table = data.get("mapping_table_suggestion", [])
            unmapped_src = data.get("unmapped_source", [])
            unmapped_tgt = data.get("unmapped_target", [])
            explanation = data.get("explanation", "")
            errors = data.get("validation_errors", 0)
            warnings = data.get("validation_warnings", 0)

            lamp_emoji = {"GREEN": "✅", "ORANGE": "🟡", "RED": "🔴"}.get(lamp, "❓")
            lamp_label = {"GREEN": "Compatible", "ORANGE": "Partiel", "RED": "Incompatible"}.get(lamp, lamp)

            lines = [
                f"## {lamp_emoji} Comparaison: *{title_a}* vs *{title_b}*",
                "",
                f"**Score global:** `{score:.2f}` | **Statut:** {lamp_label} | **Erreurs:** {errors} | **Avertissements:** {warnings}",
                "",
            ]

            if join_candidates:
                lines.append(f"### Cles de jointure ({len(join_candidates)})")
                lines.append("")
                lines.append("| Champ A | Champ B | Concept I14Y | Score | Statut |")
                lines.append("|---------|---------|--------------|-------|--------|")
                for jp in join_candidates:
                    field_lamp = {"GREEN": "✅", "ORANGE": "🟡", "RED": "🔴"}.get(jp.get("lamp", "RED"), "❓")
                    hint = jp.get("transformation_hint") or ""
                    hint_str = f" *({hint})*" if hint else ""
                    lines.append(
                        f"| `{jp['source_field']}` | `{jp['target_field']}` "
                        f"| {jp['shared_concept_name']}{hint_str} | {jp['confidence']:.2f} | {field_lamp} |"
                    )
                lines.append("")

            if unmapped_src:
                lines.append(f"**Champs non mappes (A):** {', '.join(f'`{f}`' for f in unmapped_src)}")
            if unmapped_tgt:
                lines.append(f"**Champs non mappes (B):** {', '.join(f'`{f}`' for f in unmapped_tgt)}")
            if unmapped_src or unmapped_tgt:
                lines.append("")

            if mapping_table:
                lines.append(f"### Table de mapping I14Y suggeree ({len(mapping_table)} lignes)")
                lines.append("")
                lines.append("| Concept A | Concept B | Transformation | Score |")
                lines.append("|-----------|-----------|----------------|-------|")
                for row in mapping_table:
                    lines.append(
                        f"| {row['source_concept_name']} | {row['target_concept_name']}"
                        f" | {row['transformation_rule']} | {row['confidence']:.2f} |"
                    )
                lines.append("")
                lines.append("> Soumettez cette table sur **https://www.i14y.admin.ch** pour enrichir le catalogue national.")
                lines.append("")

            if explanation:
                lines.append(f"**Analyse:** {explanation}")
                lines.append("")

            ogd_a = data.get("dataset_a_ogd", True)
            ogd_b = data.get("dataset_b_ogd", True)
            if lamp in ("GREEN", "ORANGE"):
                if ogd_a and ogd_b:
                    lines.append("> Tapez **`harmoniser`** pour generer le fichier CSV fusionne.")
                    lines.append("> Tapez **`exporter table mapping`** pour telecharger les correspondances.")
                else:
                    lines.append("> ⚠️ Un dataset n\\'a pas de distribution publique — harmonisation indisponible.")

            return "\\n".join(lines)

        except Exception as e:
            return f"Erreur lors de la comparaison: {e}"
'''

COMPARE_SPECS = json.dumps([
    {
        "name": "compare_datasets",
        "description": "Compare deux datasets I14Y et retourne un score de compatibilite avec systeme de validation vert/orange/rouge, cles de jointure et suggestions de table de mapping I14Y.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_a_id": {
                    "type": "string",
                    "description": "Identifiant I14Y du premier dataset (UUID ou identifiant court comme 'SpiGes_Administratives')"
                },
                "dataset_b_id": {
                    "type": "string",
                    "description": "Identifiant I14Y du deuxieme dataset"
                }
            },
            "required": ["dataset_a_id", "dataset_b_id"]
        }
    }
])

# ─── Tool: dataset_schema ─────────────────────────────────────────────────────
SCHEMA_TOOL_ID = "dataset_schema"
SCHEMA_CONTENT = '''"""
title: Schema Dataset I14Y
description: Recupere et affiche la structure (champs, types) d\'un dataset I14Y. Supporte le fallback OGD automatique.
author: semantic-bridge
version: 1.0.0
"""

import httpx


class Tools:
    FASTAPI_BASE = "http://localhost:8000"

    def get_dataset_schema(self, dataset_id: str) -> str:
        """
        Recupere la structure d\'un dataset I14Y (liste des champs et types de donnees).
        Fonctionne pour les datasets avec structure definie ET les datasets OGD (lecture du fichier de distribution).

        :param dataset_id: Identifiant I14Y du dataset (UUID ou identifiant court)
        :return: Liste des champs et types du dataset
        """
        try:
            r = httpx.get(
                f"{self.FASTAPI_BASE}/dataset/{dataset_id}/structure",
                timeout=30,
            )
            if r.status_code == 200:
                data = r.json()
                if "error" in data:
                    return f"Erreur: {data[\'error\']}"
                title = data.get("title", dataset_id)
                fields = data.get("schema", {}).get("fields", [])
                field_count = data.get("field_count", len(fields))
                identifier = data.get("identifier", dataset_id)

                lines = [
                    f"### Schema: {title}",
                    f"**ID:** `{identifier}` | **Champs:** {field_count}",
                    "",
                    "| # | Champ | Type |",
                    "|---|-------|------|",
                ]
                for i, f in enumerate(fields, 1):
                    lines.append(f"| {i} | `{f[\'name\']}` | {f.get(\'data_type\', \'UNKNOWN\')} |")

                if not fields:
                    lines.append("| — | *Aucun champ structure trouve* | — |")

                return "\\n".join(lines)
            return f"Erreur API: HTTP {r.status_code}"
        except Exception as e:
            return f"Erreur: {e}"
'''

SCHEMA_SPECS = json.dumps([
    {
        "name": "get_dataset_schema",
        "description": "Recupere la structure (champs et types) d'un dataset I14Y. Utiliser avant compare_datasets pour inspecter les champs.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "Identifiant I14Y du dataset (UUID ou identifiant court)"
                }
            },
            "required": ["dataset_id"]
        }
    }
])

# ─── Tool: harmonize_datasets ─────────────────────────────────────────────────
HARMONIZE_TOOL_ID = "harmonize_datasets"
HARMONIZE_CONTENT = '''"""
title: Harmonisation Datasets I14Y
description: Fusionne deux datasets I14Y OGD en un fichier CSV harmonise. Necessite des datasets avec distribution publique.
author: semantic-bridge
version: 1.0.0
"""

import httpx


class Tools:
    FASTAPI_BASE = "http://localhost:8000"

    def harmonize_datasets(self, dataset_a_id: str, dataset_b_id: str) -> str:
        """
        Fusionne deux datasets I14Y OGD en un fichier CSV harmonise via les concepts I14Y communs.
        Applique automatiquement les transformations necessaires et merge sur les cles de jointure.
        Necessite que les deux datasets aient une distribution publique (OGD).

        :param dataset_a_id: Identifiant I14Y du premier dataset
        :param dataset_b_id: Identifiant I14Y du deuxieme dataset
        :return: Statistiques du fichier genere et lien de telechargement
        """
        try:
            r = httpx.post(
                f"{self.FASTAPI_BASE}/harmonize",
                json={"dataset_a_id": dataset_a_id, "dataset_b_id": dataset_b_id, "output_format": "csv"},
                timeout=120,
            )
            if r.status_code == 200:
                # Content-Disposition header contains the filename
                content_disp = r.headers.get("content-disposition", "")
                filename = "harmonized.csv"
                if "filename=" in content_disp:
                    filename = content_disp.split("filename=")[-1].strip(\'"; \')

                # Count rows (approximate from CSV content)
                csv_text = r.text
                lines = [l for l in csv_text.split("\\n") if l and not l.startswith("#")]
                rows = max(0, len(lines) - 1)  # minus header row
                cols = len(lines[0].split(",")) if lines else 0

                return (
                    f"✅ **Fichier harmonise genere avec succes!**\\n\\n"
                    f"- **Lignes fusionnees:** {rows}\\n"
                    f"- **Colonnes:** {cols}\\n"
                    f"- **Fichier:** `{filename}`\\n\\n"
                    f"Le fichier inclut des colonnes de provenance (`_source_a`, `_source_b`, `_merged_at`, `_score`).\\n"
                    f"Utilisez `GET /harmonize` avec les memes parametres pour telecharger directement."
                )
            elif r.status_code == 422:
                detail = r.json().get("detail", r.text[:200])
                return f"🔴 **Harmonisation impossible:** {detail}"
            else:
                return f"Erreur API: HTTP {r.status_code} — {r.text[:200]}"
        except Exception as e:
            return f"Erreur lors de l\'harmonisation: {e}"
'''

HARMONIZE_SPECS = json.dumps([
    {
        "name": "harmonize_datasets",
        "description": "Fusionne deux datasets I14Y OGD en un fichier CSV harmonise. A appeler apres compare_datasets si la lampe est verte ou orange.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_a_id": {
                    "type": "string",
                    "description": "Identifiant I14Y du premier dataset"
                },
                "dataset_b_id": {
                    "type": "string",
                    "description": "Identifiant I14Y du deuxieme dataset"
                }
            },
            "required": ["dataset_a_id", "dataset_b_id"]
        }
    }
])

# ─── Tool: export_mapping_table ───────────────────────────────────────────────
EXPORT_TOOL_ID = "export_mapping_table"
EXPORT_CONTENT = '''"""
title: Export Table de Mapping I14Y
description: Genere et affiche une table de mapping I14Y suggeree entre deux datasets. Peut etre soumise sur i14y.admin.ch.
author: semantic-bridge
version: 1.0.0
"""

import httpx
import json


class Tools:
    FASTAPI_BASE = "http://localhost:8000"

    def export_mapping_table(self, dataset_a_id: str, dataset_b_id: str) -> str:
        """
        Genere une table de mapping I14Y entre deux datasets et affiche les correspondances suggeres.
        La table peut etre soumise manuellement sur https://www.i14y.admin.ch pour enrichir le catalogue national.

        :param dataset_a_id: Identifiant I14Y du premier dataset
        :param dataset_b_id: Identifiant I14Y du deuxieme dataset
        :return: Table de mapping en Markdown avec lien de soumission I14Y
        """
        try:
            r = httpx.post(
                f"{self.FASTAPI_BASE}/compare/export-mapping-table",
                json={"dataset_a_id": dataset_a_id, "dataset_b_id": dataset_b_id, "format": "json"},
                timeout=60,
            )
            if r.status_code == 200:
                data = r.json()
                mappings = data.get("mappings", [])
                title_a = data.get("dataset_a", {}).get("title", dataset_a_id)
                title_b = data.get("dataset_b", {}).get("title", dataset_b_id)

                lines = [
                    f"### Table de mapping I14Y: *{title_a}* → *{title_b}*",
                    f"**{len(mappings)} correspondance(s) suggeree(s)**",
                    "",
                    "| Concept Source | Concept Cible | Champ A | Champ B | Transformation | Score |",
                    "|----------------|---------------|---------|---------|----------------|-------|",
                ]
                for m in mappings:
                    lines.append(
                        f"| {m['source_concept_name']} | {m['target_concept_name']}"
                        f" | `{m['source_field']}` | `{m['target_field']}`"
                        f" | {m['transformation_rule']} | {m['confidence']:.2f} |"
                    )
                lines.append("")
                lines.append(
                    "💡 **Soumettez cette table sur [i14y.admin.ch](https://www.i14y.admin.ch)** "
                    "pour enrichir le catalogue national d\'interoperabilite suisse."
                )
                return "\\n".join(lines)
            elif r.status_code == 404:
                return "ℹ️ Aucune table de mapping necessaire — les datasets sont directement compatibles (pas de transformation requise)."
            elif r.status_code == 422:
                detail = r.json().get("detail", r.text[:200])
                return f"Impossible de generer la table: {detail}"
            return f"Erreur API: HTTP {r.status_code}"
        except Exception as e:
            return f"Erreur: {e}"
'''

EXPORT_SPECS = json.dumps([
    {
        "name": "export_mapping_table",
        "description": "Genere une table de mapping I14Y suggeree entre deux datasets. A appeler quand la comparaison montre une lampe orange (transformation requise).",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_a_id": {
                    "type": "string",
                    "description": "Identifiant I14Y du premier dataset"
                },
                "dataset_b_id": {
                    "type": "string",
                    "description": "Identifiant I14Y du deuxieme dataset"
                }
            },
            "required": ["dataset_a_id", "dataset_b_id"]
        }
    }
])

now = int(time.time())

# Register all tools
tools = [
    (COMPARE_TOOL_ID, "Comparaison Datasets I14Y", COMPARE_CONTENT, COMPARE_SPECS),
    (SCHEMA_TOOL_ID, "Schema Dataset I14Y", SCHEMA_CONTENT, SCHEMA_SPECS),
    (HARMONIZE_TOOL_ID, "Harmonisation Datasets I14Y", HARMONIZE_CONTENT, HARMONIZE_SPECS),
    (EXPORT_TOOL_ID, "Export Table Mapping I14Y", EXPORT_CONTENT, EXPORT_SPECS),
]

for tool_id, name, content, specs in tools:
    meta = json.dumps({
        "description": f"{name} — semantic-bridge",
        "manifest": {"title": name, "author": "semantic-bridge", "version": "1.0.0"},
    })
    conn.execute(
        """INSERT OR REPLACE INTO tool (id, user_id, name, content, specs, meta, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (tool_id, user_id, name, content, specs, meta, now, now)
    )
    print(f"[OK] Tool '{tool_id}' enregistre")

conn.commit()

# Assign all 5 tools to the Apertus model (keep existing i14y_search)
ALL_TOOL_IDS = ["i14y_search", COMPARE_TOOL_ID, SCHEMA_TOOL_ID, HARMONIZE_TOOL_ID, EXPORT_TOOL_ID]

row = conn.execute("SELECT params, meta FROM model WHERE id = ?", (TARGET_MODEL,)).fetchone()
if row:
    params = json.loads(row[0]) if row[0] else {}
    meta = json.loads(row[1]) if row[1] else {}
    params["tool_ids"] = ALL_TOOL_IDS
    meta["capabilities"] = {"vision": False, "usage": True, "citations": False, "tools": True}
    conn.execute(
        "UPDATE model SET params = ?, meta = ? WHERE id = ?",
        (json.dumps(params), json.dumps(meta), TARGET_MODEL)
    )
    conn.commit()
    print(f"[OK] Modele '{TARGET_MODEL}' mis a jour avec {len(ALL_TOOL_IDS)} tools")
else:
    print(f"[WARN] Modele '{TARGET_MODEL}' non trouve")

# Pre-enable all tools for all users
users = conn.execute("SELECT id FROM user").fetchall()
for (uid,) in users:
    r = conn.execute("SELECT settings FROM user WHERE id = ?", (uid,)).fetchone()
    settings = json.loads(r[0]) if r[0] else {}
    if "ui" not in settings:
        settings["ui"] = {}
    settings["ui"]["toolIds"] = ALL_TOOL_IDS
    settings["ui"]["selectedToolIds"] = ALL_TOOL_IDS
    settings["ui"]["showTools"] = True
    conn.execute("UPDATE user SET settings = ? WHERE id = ?", (json.dumps(settings), uid))
conn.commit()
print(f"[OK] {len(ALL_TOOL_IDS)} tools pre-actives pour {len(users)} utilisateur(s)")

conn.close()
print("\n[INFO] Redemarrer Open WebUI pour charger les nouveaux tools.")
