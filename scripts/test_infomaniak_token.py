import httpx
from core.config import get_settings

s = get_settings()
token = s.infomaniak_api_key
product_id = s.infomaniak_product_id

print(f"INFOMANIAK_API_KEY : {'OK (definie)' if token else 'MANQUANTE'}")
print(f"INFOMANIAK_PRODUCT_ID : {product_id if product_id else 'MANQUANTE'}")

if not token or not product_id:
    print("\nERREUR : completez le .env avant de tester.")
    raise SystemExit(1)

# Test: endpoint AI chat completions (OpenAI-compatible)
url = f"https://api.infomaniak.com/2/ai/{product_id}/openai/v1/chat/completions"
print(f"\nTest endpoint : {url}")

ai_resp = httpx.post(
    url,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    json={
        "model": s.infomaniak_model,
        "messages": [{"role": "user", "content": "Reponds uniquement avec: OK"}],
        "max_tokens": 10,
    },
    timeout=20,
)
print(f"Status AI : {ai_resp.status_code}")
if ai_resp.status_code == 200:
    result = ai_resp.json()
    msg = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    model = result.get("model", "?")
    print(f"Modele : {model}")
    print(f"Reponse : {msg}")
    print("\nInfomaniak AI operationnel !")
else:
    print(f"Erreur : {ai_resp.text[:500]}")
