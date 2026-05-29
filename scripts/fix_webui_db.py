"""Fix Open WebUI DB: correct default model, disable Ollama, fix MCP path duplication."""
import sqlite3
import json

DB_PATH = r"C:\Users\sanfa\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db"
TARGET_MODEL = "i14y-discovery-swiss-ai-apertus-70b-instruct-2509"
INFOMANIAK_URL = "https://api.infomaniak.com/2/ai/108975/openai/v1"

# Chat-only models to expose — embedding models excluded
CHAT_MODELS = [
    "swiss-ai/Apertus-70B-Instruct-2509",
    "mistralai/Ministral-3-14B-Instruct-2512",
    "mistralai/Mistral-Small-4-119B-2603",
    "Qwen/Qwen3.5-122B-A10B-FP8",
    "google/gemma-4-31B-it",
    "moonshotai/Kimi-K2.6",
    "moonshotai/Kimi-K2.5",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
]

conn = sqlite3.connect(DB_PATH)
try:
    row = conn.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        print("No config row found.")
        raise SystemExit(1)

    cfg_id, data_str = row
    data = json.loads(data_str)

    # 1) Set default model so new chats use Apertus instead of Ollama models
    data.setdefault("ui", {})["default_models"] = TARGET_MODEL
    print(f"[OK] ui.default_models = {TARGET_MODEL}")

    # 2) Disable Ollama
    data["ollama"] = {"enable": False, "base_urls": []}
    print("[OK] ollama.enable = False")

    # 3) Filter Infomaniak models: only show chat models, exclude embedding models
    #    (bge_multilingual_gemma2, mini_lm_l12_v2, Qwen/Qwen3-Embedding-8B, etc.)
    data.setdefault("openai", {})["api_configs"] = {
        INFOMANIAK_URL: {"model_ids": CHAT_MODELS}
    }
    print(f"[OK] openai.api_configs.model_ids set ({len(CHAT_MODELS)} chat models)")

    # 3) Fix MCP path: i14y_mcp_url already ends with /mcp,
    #    setting path='/mcp' would double it to /mcp/mcp
    tool_conns = data.get("tool_server", {}).get("connections", [])
    for item in tool_conns:
        if isinstance(item, dict):
            # Fix null config/info
            if item.get("config") is None:
                item["config"] = {}
            if item.get("info") is None:
                item["info"] = {}
            # Remove duplicate /mcp from path
            if "mcp.i14y" in item.get("url", "") and item.get("path") == "/mcp":
                item["path"] = ""
                print(f"[OK] MCP path cleared for {item['url']}")

    conn.execute("UPDATE config SET data = ? WHERE id = ?", (json.dumps(data), cfg_id))
    conn.commit()

    # 4) Enable tool calling on the Apertus model
    model_row = conn.execute(
        "SELECT params, meta FROM model WHERE id = ?", (TARGET_MODEL,)
    ).fetchone()
    if model_row:
        m_params = json.loads(model_row[0]) if model_row[0] else {}
        m_meta = json.loads(model_row[1]) if model_row[1] else {}
        m_meta["capabilities"] = {
            "vision": False,
            "usage": True,
            "citations": False,
            "tools": True,
        }
        m_params.setdefault("tool_ids", [])
        conn.execute(
            "UPDATE model SET params = ?, meta = ? WHERE id = ?",
            (json.dumps(m_params), json.dumps(m_meta), TARGET_MODEL),
        )
        conn.commit()
        print("[OK] capabilities.tools = True pour le modele Apertus")

    print("\nAll fixes applied. Restart Open WebUI for changes to take effect.")
finally:
    conn.close()
