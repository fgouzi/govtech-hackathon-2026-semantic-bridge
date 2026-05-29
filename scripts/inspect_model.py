"""Full model params/meta inspection."""
import sqlite3
import json

DB = r"C:\Users\sanfa\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db"
conn = sqlite3.connect(DB)

row = conn.execute(
    "SELECT params, meta FROM model WHERE id = ?",
    ("i14y-discovery-swiss-ai-apertus-70b-instruct-2509",)
).fetchone()

params = json.loads(row[0]) if row[0] else {}
meta = json.loads(row[1]) if row[1] else {}

print("=== PARAMS ===")
# Don't print full system prompt
p2 = dict(params)
if "system" in p2:
    p2["system"] = p2["system"][:80] + "..."
print(json.dumps(p2, indent=2, ensure_ascii=False))

print("\n=== META ===")
print(json.dumps(meta, indent=2, ensure_ascii=False))
conn.close()
