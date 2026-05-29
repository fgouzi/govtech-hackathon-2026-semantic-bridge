"""Page 6: Validation report — errors and warnings in the mapping plan."""

import httpx
import streamlit as st

st.set_page_config(page_title="Validation Report — Semantic Bridge", layout="wide")
st.title("✅ Validation Report")
st.caption("Check your mapping plan for errors, warnings, and potential issues.")

api_url = st.session_state.get("api_url", "http://localhost:8000")
plan = st.session_state.get("mapping_plan")

if not plan:
    st.warning("No mapping plan found. Run **Semantic Matching** first.")
    st.stop()

if st.button("🔍 Run Validation", type="primary"):
    with st.spinner("Validating mapping plan..."):
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{api_url}/validate", json={"mapping": plan})
                if resp.status_code == 200:
                    st.session_state.validation_report = resp.json()
                    st.success("Validation complete!")
                else:
                    st.error(f"API error: {resp.text}")
        except httpx.ConnectError:
            st.error("Cannot connect to API.")

report = st.session_state.get("validation_report")
if report:
    passed = report.get("passed", False)
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])

    # Summary
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Status", "✅ PASSED" if passed else "❌ FAILED")
    with col2:
        st.metric("Errors", len(errors), delta=None)
    with col3:
        st.metric("Warnings", len(warnings), delta=None)

    st.divider()

    if not errors and not warnings:
        st.success("🎉 Perfect mapping! No issues found.")

    if errors:
        st.subheader("❌ Errors")
        for issue in errors:
            with st.expander(f"[{issue['issue']}] {issue['field']}"):
                st.error(issue["detail"])

    if warnings:
        st.subheader("⚠️ Warnings")
        for issue in warnings:
            with st.expander(f"[{issue['issue']}] {issue['field']}"):
                st.warning(issue["detail"])

    # Issue type legend
    st.divider()
    st.subheader("Issue Types")
    st.markdown("""
| Code | Severity | Meaning |
|---|---|---|
| `missing_mapping` | Error | Field has no matched concept |
| `low_confidence` | Error/Warning | Confidence below threshold |
| `type_mismatch` | Warning | Source and concept types may be incompatible |
| `duplicate_target` | Warning | Two fields mapped to same concept |
""")
