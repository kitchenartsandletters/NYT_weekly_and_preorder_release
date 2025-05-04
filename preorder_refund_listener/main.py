from fastapi import FastAPI, Request, HTTPException
import os
import os.path
import json
import hmac
import hashlib
import base64
import utils
 # Load environment variables from the root .env.production
env_file = os.getenv('ENV_FILE', os.path.join(os.path.dirname(__file__), '..', '.env.production'))
from dotenv import load_dotenv

# Load environment
load_dotenv(env_file)

SHOPIFY_WEBHOOK_SECRET = os.getenv('SHOPIFY_WEBHOOK_SECRET')

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/webhook/orders/update")
async def handle_order_update(request: Request):
    raw_body = await request.body()
    # Validate HMAC signature
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256', '')
    computed_hmac = base64.b64encode(
        hmac.new(
            SHOPIFY_WEBHOOK_SECRET.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    if not hmac.compare_digest(computed_hmac, hmac_header):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")

    payload = json.loads(raw_body)
    # Process refund or cancellation
    result = utils.process_refund_event(payload)
    return {"processed": result}
