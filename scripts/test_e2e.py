"""End-to-end test: Open WebUI chat → Apertus → FastAPI search → I14Y."""
from __future__ import annotations
import httpx
import json
import sys

sys.path.insert(0, ".")

WEBUI = "http://localhost:8080"
FASTAPI = "http://localhost:8000"


def step(n: int, label: str, ok: bool, detail: str = "") -> None:
    icon = "OK" if ok else "ECHEC"
    print(f"[{n}] {icon} {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        sys.exit(1)


def main() -> None:
    # 1. FastAPI health
    r = httpx.get(f"{FASTAPI}/health", timeout=5)
    data = r.json()
    step(1, "FastAPI", r.status_code == 200,
         f"mcp={data.get('mcp_mode')} connected={data.get('mcp_connected')}")

    # 2. Open WebUI health
    r = httpx.get(f"{WEBUI}/health", timeout=5)
    step(2, "Open WebUI", r.status_code == 200)

    # 3. Auth
    r = httpx.post(f"{WEBUI}/api/v1/auths/signin",
                   json={"email": "admin@semantic-bridge.local",
                         "password": "semantic-bridge-2026"}, timeout=10)
    token = r.json().get("token") if r.status_code == 200 else None
    step(3, "Auth WebUI", bool(token))
    headers = {"Authorization": f"Bearer {token}"}

    # 4. Model exists
    r = httpx.get(f"{WEBUI}/api/models", headers=headers, timeout=10)
    data = r.json()
    models = data.get("data", data) if isinstance(data, dict) else data
    i14y = next((m for m in models
                 if "apertus" in m.get("id", "").lower()
                 or "i14y" in m.get("id", "").lower()
                 or "decouverte" in m.get("name", "").lower()), None)
    step(4, "Modele Apertus", bool(i14y),
         i14y["id"] if i14y else f"dispo: {[m['id'] for m in models[:3]]}")
    model_id = i14y["id"] if i14y else (models[0]["id"] if models else "swiss-ai/Apertus-70B-Instruct-2509")

    # 5. Tool server configured
    r = httpx.get(f"{WEBUI}/api/v1/configs/tool_servers", headers=headers, timeout=10)
    conns = r.json().get("TOOL_SERVER_CONNECTIONS", [])
    has_fastapi = any("8000" in str(c.get("url", "")) for c in conns)
    step(5, "Tool server FastAPI", has_fastapi,
         f"{len(conns)} server(s) configure(s)")

    # 6. FastAPI search I14Y
    r = httpx.get(f"{FASTAPI}/search",
                  params={"q": "immobilier logement", "page_size": 5},
                  timeout=30)
    results = r.json() if r.status_code == 200 else {}
    items = results.get("results", [])
    step(6, "Recherche I14Y via FastAPI", r.status_code == 200 and len(items) > 0,
         f"{len(items)} résultats pour 'immobilier logement'")
    if items:
        for item in items[:3]:
            title = item.get("title") or item.get("identifier", "?")
            rtype = item.get("type", "")
            print(f"     → [{rtype}] {title}")

    # 7. Chat completions (Apertus via OpenAI-compatible endpoint)
    print("\n[7] Test chat completions (Apertus-70B)...")
    r = httpx.post(
        f"{WEBUI}/openai/chat/completions",
        headers=headers,
        json={
            "model": model_id,
            "messages": [
                {"role": "user",
                 "content": "Réponds en 1 phrase: quels datasets I14Y sur les communes suisses ?"}
            ],
            "max_tokens": 200,
            "stream": False,
        },
        timeout=60,
    )
    if r.status_code == 200:
        reply = r.json()["choices"][0]["message"]["content"]
        print(f"     Réponse ({len(reply)} chars):")
        print(f"     {reply[:300]}")
        step(7, "Chat Apertus", True)
    else:
        step(7, "Chat Apertus", False, f"HTTP {r.status_code}: {r.text[:200]}")

    print("\n=== TEST END-TO-END PASSE ===")
    print(f"  Chat: {WEBUI}")
    print(f"  API:  {FASTAPI}/docs")


if __name__ == "__main__":
    main()
