# Deployment Notes: Shopify Webhook + Railway + Procfile

## ✅ Key Findings from July 2025 Debugging Session

### 1. Procfile Syntax (Important!)
- DO NOT REMOVE QUOTES from the `Procfile` command.
- Always wrap the full Uvicorn command in double quotes to avoid syntax errors during Railway deployment:
  
```
web: "uvicorn refactor.main:app --host 0.0.0.0 --port 8080"
```

- The `--host 0.0.0.0` binding (IPv4) works reliably in Railway deployments. Do NOT use `::` (IPv6) for this project.

---

### 2. Shopify Webhook Connectivity
- Your webhook endpoint is:  
  `https://nytweeklyandpreorderrelease-production.up.railway.app/webhooks/orders_create`

- Shopify expects a **quick** HTTP 200 response from webhook endpoints.
- After the adjustments:
  - Health check endpoint returns `{ "status": "healthy" }`.
  - Shopify webhook now responds successfully with HTTP 200 `{ "status": "ok" }`.

---

### 3. Project Structure Requirements
- Ensure that `__init__.py` exists in these folders:
  - `refactor/`
  - `refactor/src/`
  - `refactor/slack/`
- These are necessary for Python to treat them as packages and for imports to work in production.

---

### 4. Railway Deployment Settings
- Root Directory in Railway should be left blank (default to repo root).
- App runs using the `Procfile`.
- No Dockerfile is necessary for this setup.

---

### 5. Testing Webhook (cURL Example)
Example cURL test to validate Shopify webhook connectivity:
```bash
curl -X POST https://nytweeklyandpreorderrelease-production.up.railway.app/webhooks/orders_create \
-H "Content-Type: application/json" \
-d '{
  "order_number": "12345",
  "customer": {
    "first_name": "John",
    "last_name": "Doe"
  },
  "line_items": [
    {
      "title": "Example Book",
      "quantity": 2
    }
  ]
}'
```

---

### ✅ Summary
This document is now the **canonical deployment reference** for this project.  
Keep it updated as the project evolves.
