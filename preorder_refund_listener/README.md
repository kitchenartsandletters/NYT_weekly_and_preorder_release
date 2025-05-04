"""
## Preorder Refund Listener

This service listens for Shopify order cancellation/refund webhooks and updates the
`preorders/NYT_preorder_tracking.csv` ledger and logs to
`preorders/preorder_refund_log.csv`.

### Setup
1. Copy `.env.production.example` to `.env.production` and configure:
   - `GITHUB_TOKEN`
   - `REPO_OWNER`
   - `REPO_NAME`
   - `GH_BRANCH`

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run locally:
   ```bash
   uvicorn main:app --reload --env-file .env.production
   ```

4. Deploy to Railway or similar using the provided `Procfile`.
"""

