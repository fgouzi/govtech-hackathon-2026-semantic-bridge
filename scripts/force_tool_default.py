"""
Force-enable i14y_search tool for all users by default in Open WebUI v0.9.x.
Patches the 'user' table settings JSON to pre-enable the tool and the tools UI toggle.
"""
import sqlite3
import json

DB = r"C:\Users\sanfa\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db"
TOOL_ID = "i14y_search"

conn = sqlite3.connect(DB)

# Show all users
users = conn.execute("SELECT id, email, settings FROM user").fetchall()
print(f"Found {len(users)} user(s)")

for uid, email, settings_raw in users:
    settings = json.loads(settings_raw) if settings_raw else {}
    print(f"\nUser: {email} (id={uid[:8]}...)")
    print(f"  Settings before: {json.dumps(settings, ensure_ascii=False)[:200]}")

    # In Open WebUI, user settings may have ui.activateTools or similar
    # Set the tool as enabled in user UI preferences
    if "ui" not in settings:
        settings["ui"] = {}

    # toolIds at user level pre-selects tools for new chats
    settings["ui"]["toolIds"] = [TOOL_ID]

    # Some versions use "selectedToolIds" 
    settings["ui"]["selectedToolIds"] = [TOOL_ID]

    # Enable tool calling in chat by default
    settings["ui"]["showTools"] = True

    conn.execute(
        "UPDATE user SET settings = ? WHERE id = ?",
        (json.dumps(settings), uid)
    )
    print(f"  Settings after:  toolIds={[TOOL_ID]}, showTools=True")

# Also check the global config for default user settings
row = conn.execute("SELECT data FROM config LIMIT 1").fetchone()
if row:
    cfg = json.loads(row[0]) if row[0] else {}
    print(f"\nGlobal config ui keys: {list(cfg.get('ui', {}).keys())}")

conn.commit()
conn.close()
print("\n[OK] User settings patched — restart Open WebUI")
