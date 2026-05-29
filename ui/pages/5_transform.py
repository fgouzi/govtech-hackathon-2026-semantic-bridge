"""Page 5: Transformation preview — before/after record view."""

import httpx
import streamlit as st

st.set_page_config(page_title="Transform Preview — Semantic Bridge", layout="wide")
st.title("⚙️ Transform Preview")
st.caption("Preview how your records will look after applying the transformation plan.")

api_url = st.session_state.get("api_url", "http://localhost:8000")
plan = st.session_state.get("mapping_plan")
records = st.session_state.get("uploaded_df", [])

if not plan:
    st.warning("No mapping plan found. Run **Semantic Matching** first.")
    st.stop()

if not records:
    st.warning("No data records found. Upload a CSV in **Upload Dataset** first.")
    st.stop()

n_preview = st.slider("Records to preview", min_value=1, max_value=min(10, len(records)), value=3)
preview_records = records[:n_preview]

if st.button("⚙️ Generate Transformation", type="primary"):
    with st.spinner("Applying transformation plan..."):
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{api_url}/transform",
                    json={"mapping": plan, "records": preview_records},
                )
                if resp.status_code == 200:
                    result = resp.json()
                    st.session_state.transform_result = result
                    st.success("Transformation complete!")
                else:
                    st.error(f"API error: {resp.text}")
        except httpx.ConnectError:
            st.error("Cannot connect to API.")

if st.session_state.get("transform_result"):
    result = st.session_state.transform_result
    transformed = result.get("transformed", [])
    t_plan = result.get("plan", {})

    # Transformation rules
    rules = t_plan.get("rules", [])
    st.subheader(f"Transformation Rules ({len(rules)})")
    for rule in rules:
        op = rule.get("operation", "?")
        src = rule.get("source_field", "?")
        tgt = rule.get("target_field", "?")
        params = rule.get("params", {})
        params_str = f" {params}" if params else ""
        st.code(f"{op}: {src} → {tgt}{params_str}", language="text")

    st.divider()
    st.subheader("Before / After Comparison")

    for i, (before, after) in enumerate(zip(preview_records, transformed)):
        st.write(f"**Record {i + 1}**")
        col1, col2 = st.columns(2)
        with col1:
            st.caption("Before (original)")
            st.json(before)
        with col2:
            st.caption("After (transformed)")
            st.json(after)
        st.divider()

    # Download
    import json
    st.download_button(
        "⬇️ Download all transformed records",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name="transformed.json",
        mime="application/json",
    )
