"""Page 7: SHACL Shape-to-Shape Matching between two I14Y datasets."""

import httpx
import streamlit as st

st.set_page_config(page_title="SHACL Matching — Semantic Bridge", layout="wide")
st.title("🔗 SHACL Shape Matching")
st.caption(
    "Comparez deux datasets I14Y champ par champ — scoring sémantique + lexical + structurel."
)

api_url = st.session_state.get("api_url", "http://localhost:8000")

# ── Preset datasets ────────────────────────────────────────────────────────────
PRESETS: dict[str, dict[str, str]] = {
    "Bâtiments ↔ Logements (RegBL)": {
        "source": "88b9b0cb-3e9e-435e-9845-6cca56763874",  # BUILDING_MASTER_DATA
        "target": "87753b45-49f4-40f8-b479-e32124b1b6ad",  # DWELLING_MASTER_DATA
    },
    "Logements niveaux géo ↔ Logements canton+pièces": {
        "source": "ae78f338-6ac4-482a-a9de-99dd5361fce2",  # 36162945
        "target": "f0b144b1-edf7-4632-a32d-897b1ffe7d45",  # 36162950
    },
    "Bâtiments villes 2025 ↔ 2026": {
        "source": "4fb43c3c-a200-418f-9eee-8400019313ab",  # 35367678
        "target": "abe395d5-943e-4adc-8ded-24b32e798ded",  # 36503047
    },
    "Personnalisé": {
        "source": "",
        "target": "",
    },
}

# ── Input form ─────────────────────────────────────────────────────────────────
st.subheader("Sélection des datasets")

preset_label = st.selectbox("Paire prédéfinie", list(PRESETS.keys()), index=0)
preset = PRESETS[preset_label]
is_custom = preset_label == "Personnalisé"

col_src, col_tgt = st.columns(2)
with col_src:
    source_id = st.text_input(
        "Dataset source (UUID ou identifier I14Y)",
        value=preset["source"],
        placeholder="ex: 88b9b0cb-3e9e-435e-9845-6cca56763874",
        disabled=not is_custom,
    )
with col_tgt:
    target_id = st.text_input(
        "Dataset cible (UUID ou identifier I14Y)",
        value=preset["target"],
        placeholder="ex: 87753b45-49f4-40f8-b479-e32124b1b6ad",
        disabled=not is_custom,
    )

if is_custom:
    source_id = source_id.strip()
    target_id = target_id.strip()
else:
    source_id = preset["source"]
    target_id = preset["target"]

st.caption(
    "Les UUIDs sont ceux retournés par l'API I14Y. "
    "Utilisez la page **Explore I14Y** pour les retrouver."
)

# ── Run matching ───────────────────────────────────────────────────────────────
if st.button("🚀 Lancer le matching SHACL", type="primary", disabled=not (source_id and target_id)):
    with st.spinner("Récupération des shapes SHACL et calcul des scores…"):
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{api_url}/shacl-match",
                    json={"source_dataset_id": source_id, "target_dataset_id": target_id},
                )
            if resp.status_code == 200:
                plan = resp.json()
                st.session_state["shacl_match_plan"] = plan
                st.success("Matching terminé !")
            else:
                st.error(f"Erreur API {resp.status_code}: {resp.text[:500]}")
        except httpx.ConnectError:
            st.error("Impossible de joindre l'API. Lancez : `uv run semantic-bridge serve`")

# ── Results ────────────────────────────────────────────────────────────────────
plan = st.session_state.get("shacl_match_plan")
if plan:
    matches = plan.get("matches", [])
    src_title = plan.get("source_title", plan.get("source_dataset_id", "?"))
    tgt_title = plan.get("target_title", plan.get("target_dataset_id", "?"))

    st.divider()
    st.subheader("Résultats")
    st.markdown(f"**Source :** {src_title}  \n**Cible :** {tgt_title}")

    # Summary metrics
    overall = plan.get("overall_confidence", 0)
    high_count = plan.get("high_confidence_count", 0)
    coverage = plan.get("coverage", 0)
    total = len(matches)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score global", f"{overall:.0%}")
    m2.metric("Champs matchés (≥70%)", f"{high_count} / {total}")
    m3.metric("Couverture", f"{coverage:.0%}")
    m4.metric("Total champs source", total)

    if not matches:
        st.warning(
            "Aucun champ trouvé. Les shapes SHACL JSON-LD ne sont pas disponibles "
            "pour ces datasets sur l'API I14Y publique. "
            "Vérifiez que les UUIDs sont corrects et que le dataset expose une structure."
        )
        st.stop()

    # Filter control
    min_score = st.slider("Score minimum à afficher", 0.0, 1.0, 0.0, step=0.05)
    filtered = [m for m in matches if m["score"] >= min_score]

    # Results table
    rows = []
    for m in filtered:
        icon = "✅" if m["score"] >= 0.70 else "⚠️" if m["score"] >= 0.50 else "❌"
        rows.append(
            {
                "": icon,
                "Champ source": m["source_label"],
                "Champ cible": m["target_label"],
                "Score global": f"{m['score']:.0%}",
                "Sémantique": f"{m['score_semantic']:.0%}",
                "Lexical": f"{m['score_lexical']:.0%}",
                "Structurel": f"{m['score_structural']:.0%}",
                "Niveau": m["confidence_level"],
            }
        )

    st.dataframe(rows, use_container_width=True, height=min(600, 40 + len(rows) * 35))

    # Score distribution
    st.subheader("Distribution des scores")
    score_col1, score_col2 = st.columns(2)
    with score_col1:
        import json
        scores = [m["score"] for m in matches]
        buckets = {"≥ 70% (high)": 0, "50–70% (medium)": 0, "< 50% (low)": 0}
        for s in scores:
            if s >= 0.70:
                buckets["≥ 70% (high)"] += 1
            elif s >= 0.50:
                buckets["50–70% (medium)"] += 1
            else:
                buckets["< 50% (low)"] += 1
        st.bar_chart(buckets)

    with score_col2:
        st.markdown("**Détail des scores**")
        for label, count in buckets.items():
            pct = count / total * 100 if total else 0
            st.markdown(f"- **{label}** : {count} champs ({pct:.0f}%)")

    # Score breakdown legend
    with st.expander("ℹ️ Comment le score est calculé"):
        st.markdown(
            """
**Formule combinée :**
$$\\text{score} = 0.60 \\times \\text{sémantique} + 0.30 \\times \\text{lexical} + 0.10 \\times \\text{structurel}$$

| Composante | Méthode | Description |
|---|---|---|
| **Sémantique (60%)** | `sentence-transformers` + FAISS | Similarité cosinus entre embeddings des noms de champs |
| **Lexical (30%)** | `rapidfuzz.token_sort_ratio` | Correspondance des noms de champs (insensible à l'ordre des mots) |
| **Structurel (10%)** | Compatibilité XSD + cardinalité | Types de données (xsd:integer ↔ xsd:float ✓) et required/optional |

**Niveaux de confiance :**
- ✅ **High** (≥ 70%) — liaison directement exploitable
- ⚠️ **Medium** (50–70%) — liaison probable, vérification recommandée
- ❌ **Low** (< 50%) — liaison incertaine
"""
        )
