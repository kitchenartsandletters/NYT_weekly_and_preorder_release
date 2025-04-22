import json
import os
from datetime import datetime

HISTORY_PATH = "./preorders/preorder_history.json"

if not os.path.exists(HISTORY_PATH):
    print("❌ preorder_history.json not found.")
    exit(1)

with open(HISTORY_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

if "reported_preorders" not in data:
    print("❌ No 'reported_preorders' key found.")
    exit(1)

updated = 0
for entry in data["reported_preorders"]:
    if "title" not in entry:
        entry["title"] = "Unknown Title"
    if "inventory" not in entry:
        entry["inventory"] = 0
    if "pub_date" not in entry:
        entry["pub_date"] = ""
    if "added" not in entry:
        entry["added"] = datetime.now().isoformat()
    updated += 1

data["last_updated"] = datetime.now().isoformat()

with open(HISTORY_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"✅ Backfilled {updated} entries in preorder_history.json")