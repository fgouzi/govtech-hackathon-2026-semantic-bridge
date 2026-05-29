"""Inspect Open WebUI tools table and tool_server connection info."""
import sqlite3
import json

DB = r"C:\Users\sanfa\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db"
conn = sqlite3.connect(DB)

# Native tools (Python functions registered in Open WebUI)
rows = conn.execute("SELECT id, name, meta FROM tool LIMIT 10").fetchall()
print(f"=== NATIVE TOOLS ({len(rows)}) ===")
for r in rows:
    meta = json.loads(r[2]) if r[2] else {}
    print(f"  id={r[0]!r}  name={r[1]!r}")

# Tool server connection info field (shows if Open WebUI could connect + list tools)
row = conn.execute("SELECT data FROM config ORDER BY id DESC LIMIT 1").fetchone()
data = json.loads(row[0])
conns = data.get("tool_server", {}).get("connections", [])
print("\n=== TOOL SERVER CONNECTIONS ===")
for c in conns:
    url = c.get("url")
    info = c.get("info")
    path = c.get("path")
    print(f"  url={url!r}  path={path!r}")
    print(f"  info={json.dumps(info, indent=4)}")

conn.close()
