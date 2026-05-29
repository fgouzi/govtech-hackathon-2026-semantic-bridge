"""Page 1: Upload a CSV dataset and detect its schema."""

import pandas as pd
import streamlit as st

from domain.schema import DatasetSchema

st.set_page_config(page_title="Upload Dataset — Semantic Bridge", layout="wide")
st.title("📤 Upload Dataset")
st.caption("Upload a CSV file to detect its schema and prepare for matching.")

uploaded = st.file_uploader("Choose a CSV file", type=["csv"])

if uploaded:
    try:
        df = pd.read_csv(uploaded)
        schema = DatasetSchema.from_dataframe(df, name=uploaded.name.replace(".csv", ""))
        st.session_state.uploaded_schema = schema.model_dump()
        st.session_state.uploaded_df = df.to_dict(orient="records")

        st.success(f"Loaded **{schema.name}** — {schema.row_count} rows, {len(schema.fields)} fields")

        st.subheader("Detected Schema")
        rows = []
        for field in schema.fields:
            rows.append({
                "Field": field.name,
                "Type": field.data_type.value,
                "Nullable": "✓" if field.nullable else "✗",
                "Samples": ", ".join(field.sample_values[:3]),
            })
        st.dataframe(rows, use_container_width=True)

        st.subheader("Preview (first 5 rows)")
        st.dataframe(df.head(), use_container_width=True)

        st.info("✅ Schema saved. Go to **Semantic Matching** to match against I14Y concepts.")

    except Exception as exc:
        st.error(f"Failed to parse CSV: {exc}")

elif st.session_state.get("uploaded_schema"):
    schema_data = st.session_state.uploaded_schema
    st.info(
        f"Current schema: **{schema_data['name']}** "
        f"({len(schema_data['fields'])} fields, {schema_data['row_count']} rows)"
    )
    if st.button("Clear and upload new file"):
        st.session_state.uploaded_schema = None
        st.session_state.mapping_plan = None
        st.rerun()
else:
    st.info("No dataset uploaded yet. Upload a CSV file to begin.")
    st.subheader("Try a sample dataset")
    col1, col2 = st.columns(2)
    with col1:
        st.code("data/swiss/communes.csv\ndata/swiss/population.csv", language="text")
    with col2:
        st.code("data/enterprise/hr_employees.csv\ndata/enterprise/crm_contacts.csv", language="text")
