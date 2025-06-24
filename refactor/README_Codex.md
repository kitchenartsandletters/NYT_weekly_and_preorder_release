# 🔧 Codex Refactor Kickoff Prompt

You are starting a full Python-based refactor of the **NYT Preorder & Weekly Report System**. The original system relied heavily on file-based logic, GitHub artifacts, and brittle scripts. This refactor replaces it with a modular, database-backed, Railway-deployed service that integrates with Slack.

The spec for this project is in `refactor/refactorSpec.init`. **Do not skip this file.** Read it fully before proceeding. It contains the complete system architecture, phases, database table definitions, lifecycle rules, and pipeline expectations.

---

## ✅ Primary Objectives

1. **Migrate all preorder tracking logic** into the new modular layout.
2. **Use PostgreSQL** as the source of truth for preorders, presales, releases, and NYT reports.
3. **Replace all JSON file usage** with database persistence, unless explicitly stated in the spec (e.g., optional audit JSONs).
4. **Integrate Slack slash commands** for listing, approving, and inspecting preorder statuses using `slack/slack_handler.py`.
5. **Ensure exports for NYT reporting** match the inclusion logic described in the spec.

---

## 📁 Project Structure (Important!)

The `refactor/` folder includes:

- `/db/schema.sql` → Full database schema, including foreign keys and types
- `/src/` → Each script in here represents a functional unit described in Phase 2 of the spec
- `/slack/` → Contains `slack_handler.py` and `commands.md` reference
- `/workflows/` → GitHub Actions workflows for CI
- `/README.md` → High-level readme
- `/refactorSpec.init` → **The source of truth** for the refactor logic

---

## 🧠 Key Behavioral Expectations

- All **preorder products** are identified using the `'preorder'` tag in Shopify and live in a specific collection (handle: `'pre-order'`).  
- Presales must be recorded from order data via **Shopify webhooks or scheduled polling**.
- A book **releases** when:
  - It has reached its publication date (`pub_date`)
  - It has been approved for release (via Slack or automation)
  - It is removed from the `'preorder'` collection
- **NYT report inclusion** follows strict logic:
  - Include presales accumulated **before the release date**
  - Include **only new sales** for books already released in prior weeks
- **Anomalies** are tracked (e.g., malformed pub_date, missing tags, unexpected inventory) and stored in the database, optionally surfaced via Slack.

---

## 🔁 Data Consistency Rules

- All table relationships must be enforced by primary/foreign keys
- ISBN is the canonical identifier across the entire system
- Presales and releases must **never double-count**
- A release is **immutable** once recorded—it represents a snapshot
- NYT exports are **append-only** and timestamped

---

## 🚨 Important Notes

- You are not maintaining compatibility with legacy scripts (e.g., `main.py` at root). Start fresh.
- You **must** prioritize modularity: each function must be callable independently.
- Slack integration will grow over time. Your architecture must support extensibility.

---

## 🧪 Testing

Codex should scaffold and validate:

- Insertion and update logic for all tables (test data may be stubbed)
- Validation of inclusion/exclusion logic for NYT reports
- Edge case behavior (e.g., pub_date mismatches, duplicate ISBNs, invalid metadata)

---

## 🚀 First Deliverables (Milestone 1)

Deliver working versions of:

1. `sync_preorders.py`  
2. `record_presales.py`  
3. `analyze_readiness.py`  
4. `release_preorder.py`  
5. Initial DB connection utils in `utils/db.py`  
6. A working Slack `/preorders list` command wired into `slack_handler.py`

Each of these should be individually testable with example input (mock Shopify API response or test DB row insert).

---

## 🤖 Kickoff Task

Begin by:

- Reading `refactorSpec.init` carefully
- Loading and initializing the schema in PostgreSQL (see `db/schema.sql`)
- Scaffolding `sync_preorders.py` using mocked Shopify data to populate the `preorders` table

Confirm each step with comments and clean modular structure. Do not rush. Prioritize stability and extensibility.
