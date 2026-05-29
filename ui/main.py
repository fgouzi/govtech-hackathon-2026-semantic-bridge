"""Streamlit entry point — initialises session state and renders the home page."""

import streamlit as st

st.set_page_config(
    page_title="Semantic Bridge",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session state defaults
if "uploaded_schema" not in st.session_state:
    st.session_state.uploaded_schema = None
if "mapping_plan" not in st.session_state:
    st.session_state.mapping_plan = None
if "validation_report" not in st.session_state:
    st.session_state.validation_report = None
if "api_url" not in st.session_state:
    st.session_state.api_url = "http://localhost:8000"

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔗 Semantic Bridge")
    st.caption("Swiss I14Y Interoperability Platform")
    st.divider()
    st.subheader("Navigation")
    st.page_link("main.py", label="🏠 Accueil")
    st.page_link("pages/0_chat.py", label="💬 Assistant Chat")
    st.page_link("pages/1_upload.py", label="📂 Upload Dataset")
    st.page_link("pages/2_explore.py", label="🔍 Explorer I14Y")
    st.page_link("pages/3_matching.py", label="🧩 Matching sémantique")
    st.page_link("pages/4_review.py", label="✅ Réviser les mappings")
    st.page_link("pages/5_transform.py", label="⚙️ Transformer")
    st.page_link("pages/6_validation.py", label="📋 Validation")
    st.page_link("pages/7_shacl_match.py", label="🔷 SHACL Shape Matching")
    st.divider()
    api_url = st.text_input("API URL", value=st.session_state.api_url)
    if api_url != st.session_state.api_url:
        st.session_state.api_url = api_url

    # Health check
    try:
        import httpx
        resp = httpx.get(f"{st.session_state.api_url}/health", timeout=2.0)
        data = resp.json()
        mcp_mode = data.get("mcp_mode", "unknown")
        icon = "🟢" if mcp_mode == "live" else "🟡"
        st.caption(f"{icon} API connectée ({mcp_mode} MCP)")
    except Exception:
        st.caption("🔴 API non accessible")

# ── Hero banner ───────────────────────────────────────────────────────────────
st.title("🔗 Semantic Bridge")
st.subheader("Plateforme d'interopérabilité Swiss I14Y")

# ── Chat call-to-action ───────────────────────────────────────────────────────
st.markdown("---")

col_chat, col_info = st.columns([2, 1], gap="large")

with col_chat:
    st.markdown("### 💬 Découvrez les datasets I14Y par le chat")
    st.markdown(
        """
        Posez votre question en langage naturel — l'assistant **Apertus-70B**
        recherche dans les **604+ datasets et concepts** de la plateforme I14Y
        et vous présente une liste structurée avec scores de pertinence.
        """
    )
    st.markdown(
        """
        **Exemples de questions :**
        - *"Quels datasets sont disponibles sur l'immobilier valaisan ?"*
        - *"Données sur la santé des personnes âgées en Suisse romande"*
        - *"Datasets combinant population et communes"*
        - *"Finde Datensätze über Gebäude und Wohnungen"*
        """
    )

    # Check if Open WebUI is running
    webui_url = "http://localhost:8080"
    webui_online = False
    try:
        import httpx as _httpx
        r = _httpx.get(f"{webui_url}/health", timeout=1.5)
        webui_online = r.status_code == 200
    except Exception:
        pass

    if webui_online:
        st.link_button(
            "💬 Ouvrir le Chat — Découverte Datasets I14Y",
            url=webui_url,
            type="primary",
            use_container_width=True,
        )
        st.success("Chat disponible sur http://localhost:8080")
    else:
        st.warning(
            "**Chat non démarré.** Lancez la plateforme complète avec :\n"
            "```bash\nuv run semantic-bridge serve\n```"
        )
        st.link_button(
            "💬 Essayer quand même → http://localhost:8080",
            url=webui_url,
            use_container_width=True,
        )

with col_info:
    st.markdown("### 🛠️ Comment ça marche")
    st.markdown(
        """
        1. **Posez une question** sur un domaine thématique
        2. **Apertus-70B** (LLM souverain Infomaniak) appelle les outils MCP I14Y
        3. Les **34 outils I14Y** sont interrogés (datasets, concepts, codelistes)
        4. Les résultats sont formatés en **tableau + analyse de liaisons**
        5. Utilisez les identifiants pour charger les datasets dans les pages ci-dessous
        """
    )
    st.info(
        "**LLM:** Apertus-70B (swiss-ai, hébergé en Suisse)\n\n"
        "**Données:** I14Y — 604+ concepts, datasets et codelistes suisses"
    )

# ── Workflow Streamlit ─────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 📊 Workflow d'interopérabilité")

cols = st.columns(4)
steps = [
    ("📂", "1. Upload", "Chargez votre CSV et détectez le schéma automatiquement"),
    ("🧩", "2. Matching", "Alignez vos champs sur les concepts I14Y via IA sémantique"),
    ("⚙️", "3. Transformer", "Générez les règles de transformation et prévisualisez"),
    ("🔷", "4. SHACL", "Comparez deux datasets I14Y forme-à-forme"),
]
for col, (icon, title, desc) in zip(cols, steps):
    with col:
        st.markdown(f"**{icon} {title}**")
        st.caption(desc)

# ── Sample datasets ────────────────────────────────────────────────────────────
with st.expander("📁 Datasets d'exemple disponibles localement"):
    c1, c2 = st.columns(2)
    with c1:
        st.info("**Gouvernement suisse**\n\n`data/swiss/communes.csv`\n`data/swiss/population.csv`")
    with c2:
        st.info("**Entreprise**\n\n`data/enterprise/hr_employees.csv`\n`data/enterprise/crm_contacts.csv`")

