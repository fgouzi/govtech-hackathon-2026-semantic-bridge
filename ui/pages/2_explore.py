"""Page 2: Search I14Y datasets, concepts and data services."""

from __future__ import annotations

import httpx
import streamlit as st

st.set_page_config(page_title="Explore I14Y — Semantic Bridge", layout="wide")


# ── Helper functions (must be defined before any Streamlit rendering) ────────

def _load_dataset_schema(api_url: str, dataset_id: str, title: str) -> None:
    """Fetch dataset structure from I14Y and store as uploaded_schema."""
    with st.spinner(f"Loading schema for {title}..."):
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(f"{api_url}/dataset/{dataset_id}/structure")
            if resp.status_code == 200:
                data = resp.json()
                if "error" in data:
                    st.warning(f"I14Y returned no structure for this dataset: {data['error']}")
                    return
                schema = data.get("schema")
                field_count = data.get("field_count", 0)
                if schema and field_count > 0:
                    st.session_state["uploaded_schema"] = schema
                    st.session_state["uploaded_df"] = []
                    st.success(
                        f"Schema loaded: **{data.get('identifier', title)}** "
                        f"— {field_count} fields. Go to **Semantic Matching** to match it."
                    )
                else:
                    st.info(
                        "This dataset has no structural schema defined on I14Y yet. "
                        "You can still upload a local CSV on the **Upload Dataset** page."
                    )
            else:
                st.error(f"API error {resp.status_code}: {resp.text[:200]}")
        except httpx.ConnectError:
            st.error("Cannot connect to API. Run: `uv run semantic-bridge serve`")


def _multilang(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return (
            value.get("de") or value.get("fr") or value.get("it") or value.get("en")
            or next(iter(value.values()), "")
            or ""
        )
    return str(value) if value else ""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _relevance_stars(i: int) -> str:
    """Return ⭐ indicator based on rank position."""
    if i < 3:
        return "⭐⭐⭐"
    if i < 8:
        return "⭐⭐"
    return "⭐"


def _run_search(api_url: str, query: str, resource_type: str) -> None:
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{api_url}/search",
                params={"q": query, "resource_type": resource_type, "page_size": 20},
            )
        if resp.status_code == 200:
            st.session_state["last_search"] = resp.json()
        else:
            st.error(f"API error {resp.status_code}: {resp.text[:200]}")
    except httpx.ConnectError:
        st.error("Impossible de joindre l'API — lancez `uv run semantic-bridge serve`")


# ── Page layout ──────────────────────────────────────────────────────────────

st.title("🔍 Explorer I14Y")
st.caption(
    "Recherche bilingue FR+DE — même logique que le chat. "
    "Datasets, concepts et services de données de la plateforme suisse d'interopérabilité."
)

api_url = st.session_state.get("api_url", "http://localhost:8000")

# Search bar
col_q, col_type, col_btn = st.columns([4, 2, 1])
with col_q:
    query = st.text_input(
        "Requête",
        placeholder="ex. communes vaudoises, population santé, bâtiment registre…",
        label_visibility="collapsed",
    )
with col_type:
    resource_type = st.selectbox(
        "Type",
        options=["all", "dataset", "concept", "dataservice"],
        format_func=lambda x: {
            "all": "Toutes les ressources",
            "dataset": "Datasets uniquement",
            "concept": "Concepts uniquement",
            "dataservice": "Services de données",
        }[x],
        label_visibility="collapsed",
    )
with col_btn:
    search_clicked = st.button("Rechercher", type="primary", use_container_width=True)

st.divider()

# ── Run search ───────────────────────────────────────────────────────────────

if query and search_clicked:
    with st.spinner(f'Recherche bilingue (FR + DE) pour « {query} »…'):
        _run_search(api_url, query, resource_type)

# ── Display results ──────────────────────────────────────────────────────────

result_data = st.session_state.get("last_search")

if result_data:
    total = result_data.get("total", 0)
    results = result_data.get("results", [])
    q_display = result_data.get("query", "")

    st.subheader(f'{total} résultat(s) pour « {q_display} »')
    st.caption("Résultats fusionnés FR + DE, dédupliqués par identifiant")

    if not results:
        st.info("Aucun résultat. Essayez un autre terme ou élargissez le type de ressource.")
    else:
        # ── Tableau format (identique au chat LLM) ────────────────────────────
        TYPE_ICONS = {"dataset": "📊", "concept": "🔷", "dataservice": "⚙️"}

        # Header
        h0, h1, h2, h3, h4, h5 = st.columns([0.4, 3, 1, 2, 3, 1])
        h0.markdown("**#**")
        h1.markdown("**Titre**")
        h2.markdown("**Type**")
        h3.markdown("**Identifiant**")
        h4.markdown("**Description**")
        h5.markdown("**Pertinence**")
        st.divider()

        for i, r in enumerate(results):
            rtype = (r.get("type") or "unknown").lower()
            title = r.get("title") or r.get("identifier") or r.get("id", "")[:12]
            description = r.get("description", "")
            identifier = r.get("identifier", "")
            rid = r.get("id", "")
            publisher = r.get("publisher", "")
            type_icon = TYPE_ICONS.get(rtype, "📄")
            stars = _relevance_stars(i)

            c0, c1, c2, c3, c4, c5 = st.columns([0.4, 3, 1, 2, 3, 1])
            c0.markdown(f"{i+1}")
            c1.markdown(f"**{title[:50]}**")
            c2.markdown(f"{type_icon} `{rtype}`")
            c3.markdown(f"`{identifier[:30]}`" if identifier else f"`{rid[:12]}…`")
            c4.markdown(f"_{description[:90]}…_" if len(description) > 90 else f"_{description}_")
            c5.markdown(stars)

            # Action row (dataset only)
            if rtype == "dataset":
                with st.expander(f"Actions — {title[:40]}"):
                    ac1, ac2, ac3 = st.columns(3)
                    if ac1.button("Charger schéma", key=f"schema_{rid}", use_container_width=True):
                        _load_dataset_schema(api_url, rid or identifier, title)
                    if ac2.button("Choisir comme A", key=f"chat_a_{rid}", use_container_width=True):
                        st.session_state["chat_ds_a"] = {"id": rid or identifier, "title": title}
                        st.success(f"Dataset A défini : **{title}** — allez dans 💬 Assistant Chat")
                    if ac3.button("Choisir comme B", key=f"chat_b_{rid}", use_container_width=True):
                        st.session_state["chat_ds_b"] = {"id": rid or identifier, "title": title}
                        st.success(f"Dataset B défini : **{title}** — allez dans 💬 Assistant Chat")
                    if publisher:
                        st.caption(f"Editeur : {publisher[:80]}")

# ── Category browser (shown when no search yet) ───────────────────────────────

else:
    st.subheader("Parcourir par thème")
    st.caption("Cliquez sur un thème ou saisissez une requête ci-dessus :")

    suggestions = [
        ("Population", "population communes"),
        ("Communes", "communes territoires"),
        ("Personnes", "personne nom adresse"),
        ("Adresses", "adresse postleitzahl canton"),
        ("Économie", "entreprise emploi"),
        ("Santé", "santé hôpital patient"),
        ("Éducation", "éducation école"),
        ("Environnement", "environnement eau énergie"),
    ]
    cols = st.columns(4)
    for i, (label, suggestion_q) in enumerate(suggestions):
        with cols[i % 4]:
            if st.button(label, use_container_width=True, key=f"cat_{i}"):
                with st.spinner(f"Recherche de « {label} »…"):
                    _run_search(api_url, suggestion_q, "all")
                st.rerun()
