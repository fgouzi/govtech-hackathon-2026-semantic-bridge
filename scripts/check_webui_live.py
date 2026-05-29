"""
Apply live fixes to running Open WebUI:
1. Filter out embedding models from Infomaniak (OPENAI_API_CONFIGS)
2. Set default model to Apertus/I14Y discovery model
"""
import httpx
import json

BASE = "http://localhost:8080"
TARGET_MODEL = "i14y-discovery-swiss-ai-apertus-70b-instruct-2509"

# Chat-only models from Infomaniak (exclude embedding models)
INFOMANIAK_CHAT_MODELS = [
    "swiss-ai/Apertus-70B-Instruct-2509",
    "mistralai/Ministral-3-14B-Instruct-2512",
    "mistralai/Mistral-Small-4-119B-2603",
    "Qwen/Qwen3.5-122B-A10B-FP8",
    "google/gemma-4-31B-it",
    "moonshotai/Kimi-K2.6",
    "moonshotai/Kimi-K2.5",
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
]

# Auth
r = httpx.post(
    f"{BASE}/api/v1/auths/signin",
    json={"email": "admin@semantic-bridge.local", "password": "semantic-bridge-2026"},
    timeout=5,
)
if r.status_code != 200:
    print(f"Auth failed: {r.status_code} {r.text[:100]}")
    raise SystemExit(1)
token = r.json().get("token")
headers = {"Authorization": f"Bearer {token}"}
print("[OK] Auth token obtained")

# 1) Update OpenAI config with model_ids filter to exclude embedding models
from core.config import get_settings
s = get_settings()

payload = {
    "ENABLE_OPENAI_API": True,
    "OPENAI_API_BASE_URLS": [s.infomaniak_base_url],
    "OPENAI_API_KEYS": [s.infomaniak_api_key],
    "OPENAI_API_CONFIGS": {
        s.infomaniak_base_url: {
            "model_ids": INFOMANIAK_CHAT_MODELS,
        }
    },
}
r2 = httpx.post(f"{BASE}/openai/config/update", headers=headers, json=payload, timeout=10)
print(f"[{'OK' if r2.status_code in (200, 201) else 'ERR'}] OpenAI config update → {r2.status_code}")
if r2.status_code not in (200, 201):
    print(f"  {r2.text[:200]}")

# 2) Set default model via UI config
for endpoint, body in [
    ("/api/v1/configs/default-models", {"DEFAULT_MODELS": TARGET_MODEL}),
    ("/api/v1/configs/ui", {"DEFAULT_MODELS": TARGET_MODEL}),
]:
    r3 = httpx.post(f"{BASE}{endpoint}", headers=headers, json=body, timeout=10)
    if r3.status_code in (200, 201):
        print(f"[OK] Default model set via {endpoint}")
        break
    else:
        print(f"[--] {endpoint} → {r3.status_code}")

# 3) Verify: list models after config change
import time; time.sleep(1)
r4 = httpx.get(f"{BASE}/api/models", headers=headers, timeout=10)
if r4.status_code == 200:
    models = r4.json().get("data", [])
    print(f"\nModels after fix ({len(models)} total):")
    for m in models:
        print(f"  {m.get('id')!r}")


