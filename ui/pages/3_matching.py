"""Page 3: Semantic matching of uploaded schema."""

import httpx
import streamlit as st

st.set_page_config(page_title="Semantic Matching — Semantic Bridge", layout="wide")
st.title("🧩 Semantic Matching")
st.caption("Match your dataset schema against I14Y interoperability concepts.")

api_url = st.session_state.get("api_url", "http://localhost:8000")
schema_data = st.session_state.get("uploaded_schema")

if not schema_data:
    st.warning("No schema uploaded. Go to **Upload Dataset** first.")
    st.stop()

st.info(f"Schema: **{schema_data['name']}** — {len(schema_data['fields'])} fields")

use_ai = st.toggle("Use AI enrichment for low-confidence matches", value=True)

if st.button("🚀 Run Semantic Matching", type="primary"):
    with st.spinner("Matching schema against I14Y concepts..."):
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    f"{api_url}/match",
                    json={"schema_": schema_data, "use_ai": use_ai},
                )
                if resp.status_code == 200:
                    plan = resp.json()
                    st.session_state.mapping_plan = plan
                    st.success("Matching complete!")
                else:
                    st.error(f"API error {resp.status_code}: {resp.text}")
        except httpx.ConnectError:
            st.error("Cannot connect to API. Start with: `uv run semantic-bridge serve`")

if st.session_state.get("mapping_plan"):
    plan = st.session_state.mapping_plan
    mappings = plan.get("mappings", [])
    overall = plan.get("overall_confidence", 0)

    st.metric("Overall Confidence", f"{overall:.0%}")

    st.subheader("Matching Results")

    rows = []
    for m in mappings:
        concept = m.get("matched_concept")
        conf = m.get("confidence", 0)
        icon = "✅" if conf >= 0.7 else "⚠️" if conf >= 0.5 else "❌"
        rows.append({
            "": icon,
            "Source Field": m["source_field"],
            "I14Y Concept": concept["name"] if concept else "—",
            "Type": concept["data_type"] if concept else "—",
            "Confidence": f"{conf:.0%}",
            "Method": m.get("method", "—"),
        })
    st.dataframe(rows, use_container_width=True)

    # AI explanations
    for m in mappings:
        if m.get("explanation"):
            with st.expander(f"💬 AI explanation for '{m['source_field']}'"):
                st.write(m["explanation"])

    st.info("Proceed to **Review Mappings** to accept/reject individual mappings.")
