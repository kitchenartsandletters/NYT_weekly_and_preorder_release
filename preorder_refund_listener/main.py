from fastapi import FastAPI, Request, HTTPException
import os
env_file = os.getenv('ENV_FILE', '../env.production')
from dotenv import load_dotenv

# Load environment
load_dotenv(env_file)

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/webhook/orders/update")
async def handle_order_update(request: Request):
    payload = await request.json()
    # TODO: validate Shopify webhook signature
    # TODO: extract refund or cancellation event
    # TODO: call utils.process_refund_event(payload)
    return {"received": True}
