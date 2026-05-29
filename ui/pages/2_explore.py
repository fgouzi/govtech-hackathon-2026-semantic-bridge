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


# ── Page layout ──────────────────────────────────────────────────────────────

st.title("Explore I14Y Platform")
st.caption("Search datasets, concepts and data services from the Swiss interoperability catalog.")

api_url = st.session_state.get("api_url", "http://localhost:8000")

# Search bar
col_q, col_type, col_btn = st.columns([4, 2, 1])
with col_q:
    query = st.text_input(
        "Search query",
        placeholder="e.g. gemeinde population, person name, AHV, kanton...",
        label_visibility="collapsed",
    )
with col_type:
    resource_type = st.selectbox(
        "Type",
        options=["all", "dataset", "concept", "dataservice"],
        format_func=lambda x: {
            "all": "All resources",
            "dataset": "Datasets only",
            "concept": "Concepts only",
            "dataservice": "Data services only",
        }[x],
        label_visibility="collapsed",
    )
with col_btn:
    search_clicked = st.button("Search", type="primary", use_container_width=True)

st.divider()

# ── Run search ───────────────────────────────────────────────────────────────

if query and search_clicked:
    with st.spinner(f'Searching I14Y for "{query}"...'):
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(
                    f"{api_url}/search",
                    params={"q": query, "resource_type": resource_type, "page_size": 20},
                )
            if resp.status_code == 200:
                st.session_state["last_search"] = resp.json()
            else:
                st.error(f"API error {resp.status_code}: {resp.text[:200]}")
                st.stop()
        except httpx.ConnectError:
            st.error("Cannot connect to API. Run: `uv run semantic-bridge serve`")
            st.stop()

# ── Display results ──────────────────────────────────────────────────────────

result_data = st.session_state.get("last_search")

if result_data:
    total = result_data.get("total", 0)
    results = result_data.get("results", [])
    q_display = result_data.get("query", "")

    st.subheader(f'{total} results for "{q_display}"')

    if not results:
        st.info("No results found. Try a different query or resource type.")
    else:
        for r in results:
            rtype = r.get("type", "unknown")
            title = r.get("title") or r.get("identifier") or r.get("id", "")[:8]
            description = r.get("description", "")
            identifier = r.get("identifier", "")
            rid = r.get("id", "")
            publisher_raw = r.get("publisher", "")
            publisher = _multilang(publisher_raw) if isinstance(publisher_raw, dict) else str(publisher_raw)

            with st.expander(f"**{title}**  `{rtype}`"):
                col1, col2 = st.columns([3, 1])

                with col1:
                    if description:
                        st.write(description)
                    if identifier:
                        st.code(identifier, language="text")

                with col2:
                    if publisher:
                        st.caption(f"Publisher: {publisher[:60]}")
                    if rid:
                        st.caption(f"UUID: `{rid[:8]}…`")

                    if rtype.lower() in ("dataset",):
                        if st.button("Load schema", key=f"schema_{rid}"):
                            _load_dataset_schema(api_url, rid, title)

                    if rtype.lower() in ("codelist", "dataelement", "concept"):
                        st.caption(f"Concept ID: `{identifier}`")

# ── Category browser (shown when no search yet) ───────────────────────────────

else:
    st.subheader("Browse by category")
    st.caption("Click a category or type a query above:")

    suggestions = [
        ("Population", "bevoelkerung einwohner"),
        ("Communes", "gemeinde ortschaft"),
        ("Persons", "person name geburtsdatum"),
        ("Address", "adresse postleitzahl kanton"),
        ("Economy", "unternehmen betrieb"),
        ("Health", "gesundheit patient"),
        ("Education", "schule bildung"),
        ("Environment", "umwelt energie"),
    ]
    cols = st.columns(4)
    for i, (label, suggestion_q) in enumerate(suggestions):
        with cols[i % 4]:
            if st.button(label, use_container_width=True, key=f"cat_{i}"):
                with httpx.Client(timeout=20.0) as client:
                    try:
                        resp = client.get(
                            f"{api_url}/search",
                            params={"q": suggestion_q, "resource_type": "all", "page_size": 20},
                        )
                        if resp.status_code == 200:
                            st.session_state["last_search"] = resp.json()
                            st.rerun()
                    except Exception:
                        pass
