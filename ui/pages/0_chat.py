"""Page 0: Chat assistant intégré — recherche, sélection et harmonisation I14Y.

Layout deux colonnes :
  - Gauche  : conversation (texte pur, sans boutons dans l'historique)
  - Droite  : panneau de contrôle permanent (sélection A/B + résultats + actions)
"""

from __future__ import annotations

import httpx
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Chat — Semantic Bridge",
    page_icon="💬",
    layout="wide",
)

API_URL = st.session_state.get("api_url", "http://localhost:8000")

# ── Session state ─────────────────────────────────────────────────────────────
for _k, _v in {
    "chat_messages": [],         # [{"role": "user"|"assistant", "text": str}]
    "chat_results": [],          # derniers résultats de recherche (list[dict])
    "chat_ds_a": None,           # {"id": ..., "title": ...}
    "chat_ds_b": None,           # {"id": ..., "title": ...}
    "chat_harmonize_result": None,
    "chat_compare_result": None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── API helpers ───────────────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None, timeout: float = 30.0) -> dict | None:
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(f"{API_URL}{path}", params=params or {})
        return r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except httpx.ConnectError:
        return {"error": "API non accessible — lancez `uv run semantic-bridge serve`"}


def _post(path: str, body: dict, timeout: float = 120.0) -> dict | None:
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(f"{API_URL}{path}", json=body)
        if r.status_code == 200:
            ct = r.headers.get("content-type", "")
            return r.json() if "json" in ct else {"_csv": r.content}
        return {"error": f"HTTP {r.status_code}: {r.text[:400]}"}
    except httpx.ConnectError:
        return {"error": "API non accessible — lancez `uv run semantic-bridge serve`"}


# ── Utility ───────────────────────────────────────────────────────────────────

def _intent(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["harmonis", "fusionne", "merge", "assembl"]):
        return "harmonize"
    if any(w in t for w in ["compar", "compatib", "lampe", "score"]):
        return "compare"
    if any(w in t for w in ["structur", "schema", "champs", "colonne"]):
        return "structure"
    return "search"


def _extract_ids(text: str) -> list[str]:
    import re
    pats = [
        r'"([^"]+)"', r"'([^']+)'",
        r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
        r"\b(\d{6,}@\w+)\b",
    ]
    found: list[str] = []
    for p in pats:
        found.extend(re.findall(p, text, re.I))
    return list(dict.fromkeys(found))


def _title(item: dict) -> str:
    t = item.get("title") or item.get("identifier") or item.get("id") or "?"
    if isinstance(t, dict):
        t = t.get("fr") or t.get("de") or t.get("en") or "?"
    return str(t)


def _desc(item: dict) -> str:
    d = item.get("description", "")
    if isinstance(d, dict):
        d = d.get("fr") or d.get("de") or d.get("en") or ""
    d = str(d)
    return (d[:100] + "…") if len(d) > 100 else d


# ── Action helpers ────────────────────────────────────────────────────────────

def _do_compare(a_id: str, b_id: str) -> str:
    r = _post("/compare", {"dataset_a_id": a_id, "dataset_b_id": b_id}, timeout=60.0)
    if not r or "error" in r:
        return f"Erreur comparaison : {(r or {}).get('error', '?')}"
    st.session_state.chat_compare_result = r
    lamp = r.get("lamp", "?")
    score = r.get("overall_score", 0)
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(lamp, "⚪")
    expl = r.get("explanation", "")
    joins = [j.get("shared_concept_name") or j.get("source_field", "?") for j in r.get("join_candidates", [])[:5]]
    msg = f"{icon} **{lamp}** — Score : **{score:.0%}**\n\n{expl}"
    if joins:
        msg += f"\n\nClés candidates : {', '.join(joins)}"
    if lamp in ("GREEN", "YELLOW"):
        msg += "\n\n_✅ Compatible — cliquez **Harmoniser** dans le panneau de droite._"
    else:
        msg += "\n\n_❌ Incompatible — harmonisation bloquée._"
    return msg


def _do_harmonize(a_id: str, b_id: str) -> str:
    r = _post("/harmonize", {"dataset_a_id": a_id, "dataset_b_id": b_id, "output_format": "json"}, timeout=120.0)
    if not r or "error" in r:
        return f"Erreur harmonisation : {(r or {}).get('error', '?')}"
    if "_csv" in r:
        st.session_state.chat_harmonize_result = {"_csv": r["_csv"], "a": a_id, "b": b_id}
        return "✅ Harmonisation réussie — téléchargez le CSV dans le panneau de droite."
    meta = r.get("metadata", {})
    st.session_state.chat_harmonize_result = r
    rows = meta.get("rows_merged", "?")
    cols = meta.get("columns_merged", "?")
    score = meta.get("overall_score", 0)
    lamp = meta.get("lamp", "?")
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(lamp, "⚪")
    return (
        f"✅ **Harmonisation réussie**\n\n"
        f"- Lignes fusionnées : **{rows}**\n"
        f"- Colonnes : **{cols}**\n"
        f"- Score : **{score:.0%}** {icon}\n\n"
        "_Le tableau et le téléchargement CSV sont dans le panneau de droite._"
    )


def _process(user_text: str) -> str:
    """Traite un message utilisateur et retourne la réponse texte."""
    intent = _intent(user_text)
    ids = _extract_ids(user_text)
    ds_a = st.session_state.chat_ds_a
    ds_b = st.session_state.chat_ds_b

    if intent == "harmonize":
        if len(ids) >= 2:
            st.session_state.chat_ds_a = {"id": ids[0], "title": ids[0]}
            st.session_state.chat_ds_b = {"id": ids[1], "title": ids[1]}
            return _do_harmonize(ids[0], ids[1])
        if ds_a and ds_b:
            return _do_harmonize(ds_a["id"], ds_b["id"])
        return "Sélectionnez d'abord les datasets A et B dans le panneau à droite, puis relancez."

    if intent == "compare":
        if len(ids) >= 2:
            st.session_state.chat_ds_a = {"id": ids[0], "title": ids[0]}
            st.session_state.chat_ds_b = {"id": ids[1], "title": ids[1]}
            return _do_compare(ids[0], ids[1])
        if ds_a and ds_b:
            return _do_compare(ds_a["id"], ds_b["id"])
        return "Sélectionnez les datasets A et B dans le panneau à droite, puis relancez."

    if intent == "structure":
        target = ids[0] if ids else (ds_a or {}).get("id")
        if not target:
            return "Précisez l'identifiant du dataset."
        r = _get(f"/dataset/{target}/structure", timeout=20.0)
        if not r or "error" in r:
            return f"Erreur : {(r or {}).get('error', '?')}"
        fields = r.get("schema", {}).get("fields", [])
        lines = "\n".join(f"  - `{f['name']}` ({f.get('data_type','?')})" for f in fields[:20])
        extra = f"\n  … et {len(fields)-20} autres" if len(fields) > 20 else ""
        return f"**{r.get('title', target)}** — {len(fields)} champs\n\n{lines}{extra}"

    # default: search
    r = _get("/search", {"q": user_text, "page_size": 12, "resource_type": "all"})
    if not r or "error" in r:
        return f"Erreur : {(r or {}).get('error', '?')}"
    items = r.get("results", [])
    if not items:
        return f"Aucun résultat pour « {user_text} »."
    st.session_state.chat_results = items
    datasets_count = sum(1 for x in items if (x.get("type") or "").lower() == "dataset")
    lines = []
    for item in items[:8]:
        t = _title(item)
        rid = item.get("identifier") or item.get("id", "")
        rtype = item.get("type", "")
        lines.append(f"- **{t}** `{rid}` _{rtype}_")
    summary = f"**{len(items)} résultat(s)**" + (f" dont {datasets_count} dataset(s)" if datasets_count else "")
    hint = "\n\n_👉 Utilisez les boutons **Choisir A / Choisir B** dans le panneau de droite pour sélectionner._"
    return summary + f" pour « {user_text} »\n\n" + "\n".join(lines) + hint


# ═══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ═══════════════════════════════════════════════════════════════════════════════

col_chat, col_panel = st.columns([3, 2], gap="large")

# ══════════════════════════════════════════
# GAUCHE — CHAT
# ══════════════════════════════════════════
with col_chat:
    st.markdown("### 💬 Assistant I14Y")
    st.caption("Recherchez des datasets, comparez-les et harmonisez en langage naturel.")

    # Boutons d'exemples (visibles seulement quand le chat est vide)
    if not st.session_state.chat_messages:
        st.markdown("**Essayez :**")
        examples = [
            "Datasets sur les communes vaudoises",
            "Données population Suisse romande",
            "Comparer les deux datasets sélectionnés",
            "Harmoniser les datasets sélectionnés",
        ]
        ex_cols = st.columns(2)
        for i, ex in enumerate(examples):
            if ex_cols[i % 2].button(ex, key=f"ex_{i}", use_container_width=True):
                st.session_state.chat_messages.append({"role": "user", "text": ex})
                with st.spinner("Traitement…"):
                    reply = _process(ex)
                st.session_state.chat_messages.append({"role": "assistant", "text": reply})
                st.rerun()

    # Historique (texte pur — aucun bouton dans l'historique)
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["text"])

    # Zone de saisie
    user_input = st.chat_input("Posez une question ou entrez une commande…")
    if user_input:
        st.session_state.chat_messages.append({"role": "user", "text": user_input})
        with st.spinner("Traitement…"):
            reply = _process(user_input)
        st.session_state.chat_messages.append({"role": "assistant", "text": reply})
        st.rerun()


# ══════════════════════════════════════════
# DROITE — PANNEAU DE CONTRÔLE
# ══════════════════════════════════════════
with col_panel:

    # ── Sélection A / B ────────────────────────────────────────────────────────
    st.markdown("### 🗂️ Datasets sélectionnés")

    ds_a = st.session_state.chat_ds_a
    ds_b = st.session_state.chat_ds_b

    c1, c2 = st.columns(2)
    with c1:
        if ds_a:
            st.success(f"**A**\n\n{ds_a['title'][:28]}\n\n`{ds_a['id'][:20]}`")
        else:
            st.info("**A** — _non sélectionné_")
    with c2:
        if ds_b:
            st.success(f"**B**\n\n{ds_b['title'][:28]}\n\n`{ds_b['id'][:20]}`")
        else:
            st.info("**B** — _non sélectionné_")

    # Saisie manuelle
    with st.expander("✏️ Saisir les identifiants manuellement"):
        manual_a = st.text_input("ID Dataset A", value=ds_a["id"] if ds_a else "", key="manual_a")
        manual_b = st.text_input("ID Dataset B", value=ds_b["id"] if ds_b else "", key="manual_b")
        if st.button("Appliquer", key="apply_manual"):
            if manual_a:
                st.session_state.chat_ds_a = {"id": manual_a.strip(), "title": manual_a.strip()}
            if manual_b:
                st.session_state.chat_ds_b = {"id": manual_b.strip(), "title": manual_b.strip()}
            st.rerun()

    # Boutons d'action
    can_act = bool(ds_a and ds_b)
    btn_c1, btn_c2 = st.columns(2)

    if btn_c1.button("🔍 Comparer", type="secondary", disabled=not can_act,
                     use_container_width=True, key="btn_compare"):
        with st.spinner("Comparaison…"):
            reply = _do_compare(ds_a["id"], ds_b["id"])
        st.session_state.chat_messages.append({
            "role": "assistant",
            "text": f"**Comparaison** `{ds_a['id']}` ↔ `{ds_b['id']}`\n\n{reply}"
        })
        st.rerun()

    if btn_c2.button("⚡ Harmoniser", type="primary", disabled=not can_act,
                     use_container_width=True, key="btn_harmonize"):
        with st.spinner("Harmonisation en cours…"):
            reply = _do_harmonize(ds_a["id"], ds_b["id"])
        st.session_state.chat_messages.append({
            "role": "assistant",
            "text": f"**Harmonisation** `{ds_a['id']}` ↔ `{ds_b['id']}`\n\n{reply}"
        })
        st.rerun()

    if st.button("🗑️ Réinitialiser", use_container_width=True, key="btn_reset"):
        st.session_state.chat_ds_a = None
        st.session_state.chat_ds_b = None
        st.session_state.chat_harmonize_result = None
        st.session_state.chat_compare_result = None
        st.rerun()

    st.divider()

    # ── Résultats de recherche (cartes cliquables) ────────────────────────────
    results = st.session_state.chat_results
    if results:
        st.markdown(f"**📋 Résultats ({len(results)}) — cliquez pour sélectionner**")
        for i, item in enumerate(results):
            t = _title(item)
            rid = item.get("identifier") or item.get("id", "")
            rtype = (item.get("type") or "").lower()
            d = _desc(item)
            type_icon = {"dataset": "📊", "concept": "🔷", "dataservice": "⚙️"}.get(rtype, "📄")

            with st.container(border=True):
                st.markdown(f"{type_icon} **{t[:40]}**")
                st.caption(f"`{rid}` — {d}" if d else f"`{rid}`")
                ca, cb = st.columns(2)
                if ca.button("Choisir A", key=f"sel_a_{i}", use_container_width=True):
                    st.session_state.chat_ds_a = {"id": rid, "title": t}
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "text": f"Dataset **A** sélectionné : **{t}** (`{rid}`)"
                    })
                    st.rerun()
                if cb.button("Choisir B", key=f"sel_b_{i}", use_container_width=True):
                    st.session_state.chat_ds_b = {"id": rid, "title": t}
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "text": f"Dataset **B** sélectionné : **{t}** (`{rid}`)"
                    })
                    st.rerun()
    else:
        st.info("Faites une recherche dans le chat — les résultats apparaîtront ici avec des boutons de sélection.")

    # ── Résultat harmonisation ─────────────────────────────────────────────────
    harm = st.session_state.chat_harmonize_result
    if harm:
        st.divider()
        st.markdown("### ✅ Résultat harmonisation")
        if "_csv" in harm:
            st.download_button(
                "⬇️ Télécharger le CSV harmonisé",
                data=harm["_csv"],
                file_name="harmonized.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            meta = harm.get("metadata", {})
            m1, m2, m3 = st.columns(3)
            m1.metric("Lignes", meta.get("rows_merged", "?"))
            m2.metric("Colonnes", meta.get("columns_merged", "?"))
            m3.metric("Score", f"{meta.get('overall_score', 0):.0%}")
            if meta.get("join_keys"):
                st.caption(f"Clés de jointure : {', '.join(meta['join_keys'])}")
            data_rows = harm.get("data", [])
            if data_rows:
                df = pd.DataFrame(data_rows[:50])
                st.dataframe(df, use_container_width=True)
                if len(data_rows) > 50:
                    st.caption(f"… {len(data_rows) - 50} lignes supplémentaires")
                csv_str = pd.DataFrame(data_rows).to_csv(index=False)
                st.download_button(
                    "⬇️ Télécharger le CSV harmonisé",
                    data=csv_str,
                    file_name=f"harmonized_{meta.get('dataset_a_id','a')}_{meta.get('dataset_b_id','b')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
