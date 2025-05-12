# 🛠 Recovery Guide for preorder_history.json

This guide outlines steps for recovering from common failures related to `preorder_history.json`.

## 🚨 Scenario 1: Failed GitHub Commit

If `preorder_history.json` was updated but **not committed to the repository** due to a workflow or permissions error:

### ✅ Step 1: Pull the Latest State

From the main branch:
```bash
git pull origin main
```

### 🧪 Step 2: Locate Local `preorder_history.json`

Check if your local run produced an updated `preorder_history.json` file. If so, inspect and validate it.

### 🛠 Step 3: Commit and Push the File

```bash
git add preorder_history.json
git commit -m "Manual commit of updated preorder history from failed workflow run"
git push origin main
```

## 🔥 Scenario 2: Corrupted or Invalid Entries Were Added

You've identified:
- `isbn` and `title` were flipped or malformed
- `quantity` is incorrect or zero when it should be nonzero
- `inventory` is inaccurate (not a snapshot of live inventory)
- `pub_date` is a placeholder like `2037-01-01`

### ✅ Step 1: Open and Inspect the File

```bash
open preorder_history.json
```

Example of a problematic record:
```json
{
  "isbn": "1",
  "title": "9780593798935",
  "quantity": 0,
  "inventory": 10,
  "pub_date": "2037-01-01",
  "report_date": "2025-05-05",
  "added": "2025-05-05T15:17:07.560Z"
}
```

### 🛠 Step 2: Correct the Fields

Reference your sales data, product catalog, and current inventory to fix the entry:

```json
{
  "isbn": "9780593798935",
  "title": "Salsa Daddy: Dip Your Way into Mexican Cooking",
  "quantity": 10,
  "inventory": 37,
  "pub_date": "2025-06-03",
  "report_date": "2025-05-05",
  "added": "2025-05-05T15:17:07.560Z"
}
```

### ✅ Step 3: Validate JSON Format

Use a linter or run:
```bash
python -m json.tool preorders/preorder_history.json
```

### ✅ Step 4: Commit and Push the Fix

```bash
git add preorder_history.json
git commit -m "Fix corrupted preorder history entry for 9780593798935"
git push origin main
```

---
Stay consistent. Audit each commit with care.
