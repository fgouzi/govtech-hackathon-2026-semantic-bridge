"""Page 4: Review and edit field mappings."""

import streamlit as st

st.set_page_config(page_title="Review Mappings — Semantic Bridge", layout="wide")
st.title("✏️ Review Mappings")
st.caption("Accept or reject individual field mappings. Edit concept assignments.")

plan = st.session_state.get("mapping_plan")

if not plan:
    st.warning("No matching results found. Run **Semantic Matching** first.")
    st.stop()

mappings = plan.get("mappings", [])
st.info(f"Reviewing {len(mappings)} mappings — Overall confidence: {plan.get('overall_confidence', 0):.0%}")

updated_mappings = []
for i, m in enumerate(mappings):
    concept = m.get("matched_concept")
    conf = m.get("confidence", 0)
    conf_color = "🟢" if conf >= 0.7 else "🟡" if conf >= 0.5 else "🔴"

    with st.expander(
        f"{conf_color} **{m['source_field']}** → {concept['name'] if concept else 'No match'} ({conf:.0%})",
        expanded=conf < 0.7,
    ):
        col1, col2 = st.columns([2, 1])

        with col1:
            accepted = st.checkbox(
                "Accept this mapping",
                value=conf >= 0.5 and concept is not None,
                key=f"accept_{i}",
            )
            if concept:
                st.write(f"**Concept:** `{concept['id']}`")
                st.write(f"**Description:** {concept.get('description', '—')}")
                st.write(f"**Type:** {concept.get('data_type', '—')}")
            if m.get("explanation"):
                st.info(f"💬 {m['explanation']}")

        with col2:
            st.metric("Confidence", f"{conf:.0%}")
            st.write(f"Method: `{m.get('method', '—')}`")

        # Allow manual override of concept name
        manual_concept = st.text_input(
            "Override concept name (optional)",
            value=concept["name"] if concept and accepted else "",
            key=f"concept_override_{i}",
            placeholder="e.g. Person.FullName",
        )

        if accepted:
            if manual_concept and concept and manual_concept != concept["name"]:
                # Create a minimal concept override
                updated_concept = dict(concept)
                updated_concept["name"] = manual_concept
                updated_m = dict(m, matched_concept=updated_concept)
            else:
                updated_m = m
        else:
            updated_m = dict(m, matched_concept=None, confidence=0.0)

        updated_mappings.append(updated_m)

if st.button("💾 Save Review", type="primary"):
    updated_plan = dict(plan, mappings=updated_mappings)
    st.session_state.mapping_plan = updated_plan
    accepted_count = sum(1 for m in updated_mappings if m.get("matched_concept"))
    st.success(f"Saved! {accepted_count}/{len(updated_mappings)} mappings accepted.")
    st.info("Proceed to **Transform Preview** or **Validation Report**.")
