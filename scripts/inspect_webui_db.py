"""Inspect Open WebUI DB: models and config."""
import sqlite3
import json

DB = r"C:\Users\sanfa\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db"
conn = sqlite3.connect(DB)

# List all tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])

# Check model table
try:
    rows = conn.execute("SELECT id, name, base_model_id FROM model LIMIT 10").fetchall()
    print("\n=== MODELS ===")
    for r in rows:
        print(f"  id={r[0]!r}  name={r[1]!r}  base={r[2]!r}")
except Exception as e:
    print(f"model err: {e}")

# Check latest config
try:
    row = conn.execute("SELECT data FROM config ORDER BY id DESC LIMIT 1").fetchone()
    data = json.loads(row[0])
    ui = data.get("ui", {})
    print("\n=== UI CONFIG ===")
    print(json.dumps(ui, indent=2, ensure_ascii=False))
    openai = data.get("openai", {})
    print("\n=== OPENAI CONFIG ===")
    print("  base_urls:", openai.get("api_base_urls"))
    print("  keys count:", len(openai.get("api_keys", [])))
except Exception as e:
    print(f"config err: {e}")

conn.close()
