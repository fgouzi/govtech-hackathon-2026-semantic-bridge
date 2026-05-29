"""
Configure Open WebUI after startup via its REST API.

- Creates admin user (required even with WEBUI_AUTH=False for API access)
- Adds Infomaniak as OpenAI-compatible LLM provider
- Configures I14Y as MCP tool server
- Creates a model with the I14Y discovery system prompt
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_settings


def wait_for_webui(base_url: str, timeout: int = 60) -> bool:
    """Poll until Open WebUI is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def get_admin_token(base_url: str) -> str | None:
    """Create admin account and return JWT token."""
    # Try signin first (account may already exist)
    r = httpx.post(
        f"{base_url}/api/v1/auths/signin",
        json={"email": "admin@semantic-bridge.local", "password": "semantic-bridge-2026"},
        timeout=10,
    )
    if r.status_code == 200:
        return r.json().get("token")

    # Create account
    r = httpx.post(
        f"{base_url}/api/v1/auths/signup",
        json={
            "name": "Semantic Bridge Admin",
            "email": "admin@semantic-bridge.local",
            "password": "semantic-bridge-2026",
        },
        timeout=10,
    )
    if r.status_code == 200:
        return r.json().get("token")

    return None


def configure_llm(base_url: str, token: str, settings) -> bool:
    """Register Infomaniak as OpenAI-compatible provider."""
    headers = {"Authorization": f"Bearer {token}"}

    # Open WebUI 0.9.x: OPENAI_API_BASE_URLS (list), OPENAI_API_KEYS (list)
    payload = {
        "ENABLE_OPENAI_API": True,
        "OPENAI_API_BASE_URLS": [settings.infomaniak_base_url],
        "OPENAI_API_KEYS": [settings.infomaniak_api_key],
        "OPENAI_API_CONFIGS": {},
    }
    r = httpx.post(
        f"{base_url}/openai/config/update",
        headers=headers,
        json=payload,
        timeout=10,
    )
    if r.status_code in (200, 201):
        print(f"  LLM configure: {settings.infomaniak_base_url}")
        return True

    print(f"  LLM config status: {r.status_code} — {r.text[:200]}")
    return False


def configure_mcp(base_url: str, token: str, settings) -> bool:
    """Register I14Y as an MCP tool server."""
    headers = {"Authorization": f"Bearer {token}"}

    # Open WebUI 0.9.x: POST /api/v1/configs/tool_servers
    # with TOOL_SERVER_CONNECTIONS list
    # url already ends with /mcp — path must be empty to avoid /mcp/mcp doubling
    payload = {
        "TOOL_SERVER_CONNECTIONS": [
            {
                "url": str(settings.i14y_mcp_url),
                "path": "",
                "type": "mcp",
                "auth_type": None,
                "key": None,
                "config": {},
                "info": {},
            }
        ]
    }

    r = httpx.post(
        f"{base_url}/api/v1/configs/tool_servers",
        headers=headers,
        json=payload,
        timeout=10,
    )
    if r.status_code in (200, 201):
        print(f"  MCP serveur I14Y configure: {settings.i14y_mcp_url}")
        return True

    print(f"  MCP config status: {r.status_code} — {r.text[:200]}")
    return False


def create_i14y_model(base_url: str, token: str, settings) -> bool:
    """Create a model preset with the I14Y discovery system prompt."""
    headers = {"Authorization": f"Bearer {token}"}
    system_prompt_path = Path(__file__).parent / "system_prompt_i14y.txt"
    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    model_id = settings.infomaniak_model.replace("/", "-").replace(".", "-").lower()

    payload = {
        "id": f"i14y-discovery-{model_id}",
        "name": "Decouverte Datasets I14Y",
        "base_model_id": settings.infomaniak_model,
        "params": {
            "system": system_prompt,
            "temperature": 0.1,
            "max_tokens": 4096,
        },
        "meta": {
            "description": "Assistant specialise dans la decouverte de datasets I14Y. Pose une question thematique (ex: 'datasets sur l'immobilier valaisan') et l'assistant recherche et structure les resultats.",
            "tags": ["i14y", "datasets", "suisse", "interoperabilite"],
            "capabilities": {
                "vision": False,
                "usage": True,
                "citations": False,
                "tools": True,
            },
        },
    }

    # Open WebUI 0.9.x: POST /api/v1/models/create
    r = httpx.post(
        f"{base_url}/api/v1/models/create",
        headers=headers,
        json=payload,
        timeout=10,
    )
    if r.status_code in (200, 201):
        print(f"  Modele 'Decouverte Datasets I14Y' cree")
        return True

    # Try update if already exists
    model_id = payload["id"]
    r = httpx.post(
        f"{base_url}/api/v1/models/model/update",
        headers=headers,
        json=payload,
        params={"id": model_id},
        timeout=10,
    )
    if r.status_code in (200, 201):
        print(f"  Modele 'Decouverte Datasets I14Y' mis a jour")
        return True
    print(f"  Modele config status: {r.status_code} — {r.text[:200]}")
    return False


def disable_ollama(base_url: str, token: str) -> bool:
    """Disable Ollama to prevent embedding models from appearing as chat models."""
    headers = {"Authorization": f"Bearer {token}"}
    r = httpx.post(
        f"{base_url}/ollama/config/update",
        headers=headers,
        json={"ENABLE_OLLAMA_API": False},
        timeout=10,
    )
    return r.status_code in (200, 201)


def set_default_model(base_url: str, token: str, model_id: str) -> bool:
    """Set the default model for new chats via the UI config endpoint."""
    headers = {"Authorization": f"Bearer {token}"}
    # Try the direct config endpoint first (Open WebUI 0.6+)
    r = httpx.post(
        f"{base_url}/api/v1/configs/ui",
        headers=headers,
        json={"DEFAULT_MODELS": model_id},
        timeout=10,
    )
    if r.status_code in (200, 201):
        return True
    # Fallback: update via SQLite directly
    import sqlite3, json as _json
    import glob
    dbs = glob.glob(r"C:\Users\*\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db")
    if not dbs:
        return False
    db_path = dbs[0]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return False
        cfg_id, data_str = row
        data = _json.loads(data_str)
        data.setdefault("ui", {})["default_models"] = model_id
        conn.execute("UPDATE config SET data = ? WHERE id = ?", (_json.dumps(data), cfg_id))
        conn.commit()
        return True
    finally:
        conn.close()


def main(webui_port: int | None = None) -> None:
    settings = get_settings()
    port = webui_port or settings.open_webui_port
    base_url = f"http://localhost:{port}"

    print(f"Configuration de Open WebUI sur {base_url}...")

    if not wait_for_webui(base_url, timeout=90):
        print(f"  ERREUR: Open WebUI non accessible sur {base_url} apres 90s")
        sys.exit(1)

    print("  Open WebUI demarre")

    token = get_admin_token(base_url)
    if not token:
        print("  INFO: Auth desactivee (WEBUI_AUTH=False) — configuration via API limitee")
        print("  Configurez le LLM et MCP manuellement: Parametres > Connexions")
        _print_manual_instructions(settings)
        return

    print("  Token admin obtenu")

    if settings.using_infomaniak:
        configure_llm(base_url, token, settings)
    elif settings.using_claude:
        print("  Claude detecte — configurez via l'UI: Parametres > Connexions > OpenAI API")

    disable_ollama(base_url, token)
    configure_mcp(base_url, token, settings)

    model_id = f"i14y-discovery-{settings.infomaniak_model.replace('/', '-').replace('.', '-').lower()}"
    create_i14y_model(base_url, token, settings)
    set_default_model(base_url, token, model_id)

    print("")
    print("Open WebUI configure!")
    print(f"  Interface chat: {base_url}")
    print(f"  Modele actif  : Decouverte Datasets I14Y (Apertus)")


def _print_manual_instructions(settings) -> None:
    print("")
    print("=== Configuration manuelle Open WebUI ===")
    print("1. Ouvrir Parametres > Connexions > API OpenAI")
    print(f"   URL  : {settings.infomaniak_base_url}")
    print(f"   Cle  : {settings.infomaniak_api_key[:8]}...")
    print("2. Ouvrir Parametres > Outils > Serveurs MCP")
    print(f"   URL  : {settings.i14y_mcp_url}")
    print("   Nom  : I14Y — Swiss Interoperability Platform")
    print("==========================================")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    main(args.port)
