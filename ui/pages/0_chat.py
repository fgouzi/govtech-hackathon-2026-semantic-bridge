"""Page 0: AI chat assistant — discover, select and harmonize I14Y datasets.

Usage examples:
- "Quels datasets sur les communes suisses ?"
- "Harmonise ds-1234 avec ds-5678"
- "Compare le dataset A avec le dataset B"
- "Montre la structure du dataset ds-1234"
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

st.set_page_config(
    page_title="Chat — Semantic Bridge",
    page_icon="💬",
    layout="wide",
)

API_URL = st.session_state.get("api_url", "http://localhost:8000")

# ── Session state ─────────────────────────────────────────────────────────────
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_pending_a" not in st.session_state:
    st.session_state.chat_pending_a = None  # dataset A awaiting confirmation
if "chat_pending_b" not in st.session_state:
    st.session_state.chat_pending_b = None  # dataset B awaiting confirmation


# ── Helper: call FastAPI ───────────────────────────────────────────────────────

def _api_get(path: str, params: dict | None = None, timeout: float = 30.0) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.get(f"{API_URL}{path}", params=params or {})
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.ConnectError:
        return {"error": "API non accessible — lancez `uv run semantic-bridge serve`"}


def _api_post(path: str, body: dict, timeout: float = 120.0) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=timeout) as c:
            resp = c.post(f"{API_URL}{path}", json=body)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                return resp.json()
            # CSV or binary stream
            return {"_raw": resp.content, "_content_type": ct}
        return {"error": f"HTTP {resp.status_code}: {resp.text[:400]}"}
    except httpx.ConnectError:
        return {"error": "API non accessible — lancez `uv run semantic-bridge serve`"}


# ── Intent detection (keyword-based, no LLM call needed) ─────────────────────

def _detect_intent(text: str) -> str:
    """Return a coarse intent label from user message."""
    t = text.lower()
    if any(w in t for w in ["harmonis", "fusionne", "merge", "combiner", "assembl"]):
        return "harmonize"
    if any(w in t for w in ["compar", "compatib", "feu tricolor", "lampe", "score"]):
        return "compare"
    if any(w in t for w in ["structur", "schema", "champs", "colonne", "field"]):
        return "structure"
    if any(w in t for w in ["étape suivant", "next step", "continue", "go to", "procede"]):
        return "next_step"
    return "search"


def _extract_dataset_ids(text: str) -> list[str]:
    """Extract quoted strings or I14Y-style identifiers from user text."""
    import re
    # Match quoted strings, UUIDs, or I14Y identifier patterns like 36398596@org
    patterns = [
        r'"([^"]+)"',              # "quoted"
        r"'([^']+)'",              # 'quoted'
        r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",  # UUID
        r"\b(\d{6,}@\w+)\b",       # 36398596@org style
        r"\b(ds-\w+)\b",           # ds-123 style
    ]
    ids = []
    for pat in patterns:
        ids.extend(re.findall(pat, text, re.I))
    return list(dict.fromkeys(ids))  # deduplicate, preserve order


# ── Message renderers ─────────────────────────────────────────────────────────

def _render_search_results(results: list[dict]) -> str:
    """Format search results as markdown."""
    if not results:
        return "Aucun résultat trouvé."
    lines = []
    for r in results[:8]:
        title = r.get("title") or r.get("identifier") or r.get("id", "?")
        rid = r.get("identifier") or r.get("id", "")
        rtype = r.get("type", "")
        desc = r.get("description", "")
        if isinstance(desc, dict):
            desc = desc.get("fr") or desc.get("de") or desc.get("en") or ""
        desc_short = (desc[:100] + "…") if len(desc) > 100 else desc
        lines.append(f"- **{title}** `{rid}` _{rtype}_  \n  {desc_short}")
    return "\n".join(lines)


def _render_compare_result(result: dict) -> str:
    lamp = result.get("lamp", "?")
    score = result.get("overall_score", 0)
    explanation = result.get("explanation", "")
    joins = result.get("join_candidates", [])
    join_names = [j.get("shared_concept_name") or j.get("source_field", "?") for j in joins[:5]]
    lamp_icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(lamp, "⚪")
    text = (
        f"**Résultat de la comparaison**\n\n"
        f"{lamp_icon} Lampe : **{lamp}** — Score : **{score:.0%}**\n\n"
        f"{explanation}\n\n"
    )
    if join_names:
        text += f"**Clés de jointure candidates :** {', '.join(join_names)}\n\n"
    if lamp == "GREEN":
        text += "_✅ Compatible — vous pouvez lancer l'harmonisation._"
    elif lamp == "YELLOW":
        text += "_⚠️ Partiellement compatible — l'harmonisation est possible mais vérifiez les clés._"
    else:
        text += "_❌ Incompatible — l'harmonisation est bloquée._"
    return text


# ── Process user message ──────────────────────────────────────────────────────

def _process_message(user_text: str) -> list[dict]:
    """Return a list of assistant response dicts: {type, content, data?}."""
    intent = _detect_intent(user_text)
    ids = _extract_dataset_ids(user_text)
    responses = []

    # ── HARMONIZE ─────────────────────────────────────────────────────────────
    if intent == "harmonize":
        if len(ids) >= 2:
            a_id, b_id = ids[0], ids[1]
            responses.append({"type": "text", "content": f"🔄 Harmonisation de `{a_id}` ↔ `{b_id}` en cours…"})
            result = _api_post("/harmonize", {"dataset_a_id": a_id, "dataset_b_id": b_id, "output_format": "json"}, timeout=120.0)
            if result is None:
                responses.append({"type": "text", "content": "❌ Pas de réponse de l'API."})
            elif "error" in result:
                responses.append({"type": "text", "content": f"❌ {result['error']}"})
            elif "_raw" in result:
                # CSV response
                responses.append({"type": "download_csv", "content": "✅ Harmonisation réussie — téléchargez le fichier CSV :", "data": result["_raw"]})
            else:
                meta = result.get("metadata", {})
                data_rows = result.get("data", [])
                responses.append({"type": "harmonize_result", "content": "✅ Harmonisation réussie", "meta": meta, "data": data_rows})
        elif len(ids) == 1:
            # One ID provided — ask for the second
            st.session_state.chat_pending_a = ids[0]
            responses.append({"type": "text", "content": f"Dataset A sélectionné : `{ids[0]}`.\nQuel est le **dataset B** à harmoniser ?"})
        else:
            # No IDs — trigger a search first
            responses.append({"type": "text", "content": "🔍 Recherche de datasets pour vous aider à choisir…"})
            result = _api_get("/search", {"q": user_text, "page_size": 8, "resource_type": "dataset"})
            items = result.get("results", []) if result else []
            if items:
                responses.append({"type": "dataset_picker", "content": "Voici les datasets trouvés. **Sélectionnez deux datasets** pour les harmoniser :", "items": items})
            else:
                responses.append({"type": "text", "content": "Aucun dataset trouvé. Précisez les identifiants I14Y (ex: `\"36398596@org\"`)."})

    # ── COMPARE ───────────────────────────────────────────────────────────────
    elif intent == "compare":
        if len(ids) >= 2:
            a_id, b_id = ids[0], ids[1]
            responses.append({"type": "text", "content": f"🔍 Comparaison de `{a_id}` ↔ `{b_id}`…"})
            result = _api_post("/compare", {"dataset_a_id": a_id, "dataset_b_id": b_id}, timeout=60.0)
            if result and "error" not in result:
                responses.append({"type": "text", "content": _render_compare_result(result)})
                if result.get("lamp") in ("GREEN", "YELLOW"):
                    responses.append({
                        "type": "action_button",
                        "content": "Lancer l'harmonisation ?",
                        "action": "harmonize",
                        "dataset_a_id": a_id,
                        "dataset_b_id": b_id,
                    })
            else:
                err = result.get("error", "Erreur inconnue") if result else "Pas de réponse"
                responses.append({"type": "text", "content": f"❌ {err}"})
        else:
            responses.append({"type": "text", "content": "Précisez deux identifiants de datasets, ex : \n> _Comparer \"ds-abc\" avec \"ds-xyz\"_"})

    # ── STRUCTURE ─────────────────────────────────────────────────────────────
    elif intent == "structure":
        if ids:
            ds_id = ids[0]
            responses.append({"type": "text", "content": f"📋 Chargement du schéma de `{ds_id}`…"})
            result = _api_get(f"/dataset/{ds_id}/structure", timeout=20.0)
            if result and "error" not in result:
                schema = result.get("schema", {})
                title = result.get("title", ds_id)
                fields = schema.get("fields", [])
                field_lines = "\n".join(f"  - `{f['name']}` ({f.get('data_type', '?')})" for f in fields[:20])
                content = f"**{title}** — {len(fields)} champs\n\n{field_lines}"
                if len(fields) > 20:
                    content += f"\n  … et {len(fields) - 20} autres"
                responses.append({"type": "text", "content": content})
            else:
                err = result.get("error", "?") if result else "Pas de réponse"
                responses.append({"type": "text", "content": f"❌ {err}"})
        else:
            responses.append({"type": "text", "content": "Précisez l'identifiant du dataset, ex : _Structure du dataset \"36398596@org\"_"})

    # ── NEXT STEP ─────────────────────────────────────────────────────────────
    elif intent == "next_step":
        a = st.session_state.get("chat_pending_a")
        b = st.session_state.get("chat_pending_b")
        if a and b:
            responses.append({"type": "text", "content": f"▶️ Lancement de l'harmonisation : `{a}` ↔ `{b}`…"})
            result = _api_post("/harmonize", {"dataset_a_id": a, "dataset_b_id": b, "output_format": "json"}, timeout=120.0)
            if result and "error" not in result and "_raw" not in result:
                meta = result.get("metadata", {})
                data_rows = result.get("data", [])
                responses.append({"type": "harmonize_result", "content": "✅ Harmonisation réussie", "meta": meta, "data": data_rows})
                st.session_state.chat_pending_a = None
                st.session_state.chat_pending_b = None
            else:
                err = result.get("error", "?") if result else "Pas de réponse"
                responses.append({"type": "text", "content": f"❌ {err}"})
        elif a:
            responses.append({"type": "text", "content": f"Dataset A : `{a}`. Quel est le **dataset B** ?"})
        else:
            responses.append({"type": "text", "content": "Aucun dataset en attente. Cherchez d'abord des datasets."})

    # ── SEARCH (default) ──────────────────────────────────────────────────────
    else:
        result = _api_get("/search", {"q": user_text, "page_size": 10, "resource_type": "all"})
        if result and "error" not in result:
            items = result.get("results", [])
            if items:
                text = f"**{len(items)} résultat(s) pour :** _{user_text}_\n\n" + _render_search_results(items)
                responses.append({"type": "text", "content": text})
                # Offer dataset selection if there are datasets in results
                datasets = [r for r in items if (r.get("type") or "").lower() == "dataset"]
                if datasets:
                    responses.append({"type": "dataset_picker", "content": "Sélectionnez des datasets pour les comparer ou harmoniser :", "items": datasets})
            else:
                responses.append({"type": "text", "content": f"Aucun résultat pour « {user_text} »."})
        else:
            err = result.get("error", "?") if result else "Pas de réponse"
            responses.append({"type": "text", "content": f"❌ {err}"})

    return responses


# ── Render chat history ───────────────────────────────────────────────────────

def _render_message(msg: dict) -> None:
    role = msg["role"]
    payload = msg["payload"]

    with st.chat_message(role):
        if isinstance(payload, str):
            st.markdown(payload)
            return

        mtype = payload.get("type", "text")

        if mtype == "text":
            st.markdown(payload["content"])

        elif mtype == "harmonize_result":
            st.success(payload["content"])
            meta = payload.get("meta", {})
            data_rows = payload.get("data", [])
            cols = st.columns(4)
            cols[0].metric("Lignes fusionnées", meta.get("rows_merged", "?"))
            cols[1].metric("Colonnes", meta.get("columns_merged", "?"))
            cols[2].metric("Score", f"{meta.get('overall_score', 0):.0%}")
            lamp = meta.get("lamp", "?")
            lamp_icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(lamp, "⚪")
            cols[3].metric("Lampe", f"{lamp_icon} {lamp}")
            if meta.get("join_keys"):
                st.caption(f"Clés de jointure : {', '.join(meta['join_keys'])}")
            if data_rows:
                import pandas as pd
                df = pd.DataFrame(data_rows[:50])
                st.dataframe(df, use_container_width=True)
                if len(data_rows) > 50:
                    st.caption(f"… {len(data_rows) - 50} lignes supplémentaires non affichées.")
                # Download button
                csv_str = pd.DataFrame(data_rows).to_csv(index=False)
                st.download_button(
                    "⬇️ Télécharger le CSV harmonisé",
                    data=csv_str,
                    file_name=f"harmonized_{meta.get('dataset_a_id','a')}_{meta.get('dataset_b_id','b')}.csv",
                    mime="text/csv",
                )

        elif mtype == "download_csv":
            st.markdown(payload["content"])
            st.download_button(
                "⬇️ Télécharger le CSV harmonisé",
                data=payload["data"],
                file_name="harmonized.csv",
                mime="text/csv",
            )

        elif mtype == "dataset_picker":
            st.markdown(payload["content"])
            items = payload.get("items", [])
            for item in items:
                title = item.get("title") or item.get("identifier") or item.get("id", "?")
                rid = item.get("identifier") or item.get("id", "")
                desc = item.get("description", "")
                if isinstance(desc, dict):
                    desc = desc.get("fr") or desc.get("de") or desc.get("en") or ""
                desc_short = (desc[:80] + "…") if len(desc) > 80 else desc
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"**{title}**  \n`{rid}`  \n_{desc_short}_")
                if c2.button("🅐 Choisir comme A", key=f"pick_a_{rid}"):
                    st.session_state.chat_pending_a = rid
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "payload": {"type": "text", "content": f"Dataset A sélectionné : `{rid}` — **{title}**"},
                    })
                    st.rerun()
                if c3.button("🅑 Choisir comme B", key=f"pick_b_{rid}"):
                    st.session_state.chat_pending_b = rid
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "payload": {"type": "text", "content": f"Dataset B sélectionné : `{rid}` — **{title}**"},
                    })
                    st.rerun()

        elif mtype == "action_button":
            st.markdown(payload["content"])
            a_id = payload.get("dataset_a_id")
            b_id = payload.get("dataset_b_id")
            if st.button(f"▶️ Harmoniser `{a_id}` ↔ `{b_id}`", key=f"action_{a_id}_{b_id}"):
                st.session_state.chat_pending_a = a_id
                st.session_state.chat_pending_b = b_id
                # Trigger harmonization in next run
                result = _api_post("/harmonize", {"dataset_a_id": a_id, "dataset_b_id": b_id, "output_format": "json"}, timeout=120.0)
                if result and "error" not in result and "_raw" not in result:
                    meta = result.get("metadata", {})
                    data_rows = result.get("data", [])
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "payload": {"type": "harmonize_result", "content": "✅ Harmonisation réussie", "meta": meta, "data": data_rows},
                    })
                else:
                    err = result.get("error", "?") if result else "Pas de réponse"
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "payload": {"type": "text", "content": f"❌ {err}"},
                    })
                st.rerun()


# ── Page layout ───────────────────────────────────────────────────────────────

st.title("💬 Assistant I14Y")
st.caption("Découvrez, comparez et harmonisez les datasets I14Y en langage naturel.")

# Status bar
col_a, col_b, col_sep = st.columns([1, 1, 2])
a_sel = st.session_state.get("chat_pending_a")
b_sel = st.session_state.get("chat_pending_b")
col_a.info(f"**Dataset A :** `{a_sel}`" if a_sel else "**Dataset A :** _non sélectionné_")
col_b.info(f"**Dataset B :** `{b_sel}`" if b_sel else "**Dataset B :** _non sélectionné_")

with col_sep:
    if a_sel and b_sel:
        if st.button(f"▶️ Harmoniser maintenant", type="primary", use_container_width=True):
            with st.spinner("Harmonisation en cours…"):
                result = _api_post("/harmonize", {"dataset_a_id": a_sel, "dataset_b_id": b_sel, "output_format": "json"}, timeout=120.0)
            if result and "error" not in result and "_raw" not in result:
                meta = result.get("metadata", {})
                data_rows = result.get("data", [])
                st.session_state.chat_messages.append({
                    "role": "user",
                    "payload": f"Harmoniser `{a_sel}` avec `{b_sel}`",
                })
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "payload": {"type": "harmonize_result", "content": "✅ Harmonisation réussie", "meta": meta, "data": data_rows},
                })
                st.session_state.chat_pending_a = None
                st.session_state.chat_pending_b = None
            else:
                err = result.get("error", "?") if result else "Pas de réponse"
                st.error(err)
            st.rerun()
    elif a_sel:
        st.caption("Sélectionnez le dataset B pour lancer l'harmonisation.")
    if a_sel or b_sel:
        if st.button("🗑️ Réinitialiser la sélection", use_container_width=True):
            st.session_state.chat_pending_a = None
            st.session_state.chat_pending_b = None
            st.rerun()

st.divider()

# ── Examples ──────────────────────────────────────────────────────────────────
with st.expander("💡 Exemples de commandes", expanded=len(st.session_state.chat_messages) == 0):
    examples = [
        "Datasets sur les communes vaudoises",
        "Comparer \"36398596@org\" avec \"45123456@org\"",
        "Harmoniser le dataset A avec le dataset B",
        "Structure du dataset \"bfs-gemeinden-2024\"",
        "Données population et santé en Suisse romande",
    ]
    cols = st.columns(len(examples))
    for col, ex in zip(cols, examples):
        if col.button(ex, use_container_width=True):
            st.session_state.chat_messages.append({"role": "user", "payload": ex})
            with st.spinner("Traitement…"):
                for resp in _process_message(ex):
                    st.session_state.chat_messages.append({"role": "assistant", "payload": resp})
            st.rerun()

# ── Render history ────────────────────────────────────────────────────────────
for msg in st.session_state.chat_messages:
    _render_message(msg)

# ── Input ─────────────────────────────────────────────────────────────────────
user_input = st.chat_input("Posez votre question ou entrez une commande…")
if user_input:
    st.session_state.chat_messages.append({"role": "user", "payload": user_input})
    with st.spinner("Traitement…"):
        responses = _process_message(user_input)
    for resp in responses:
        st.session_state.chat_messages.append({"role": "assistant", "payload": resp})
    st.rerun()
