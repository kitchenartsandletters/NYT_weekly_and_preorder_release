from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse

from .slack.slack_handler import handle_slash
from .src.record_presales import record_presales
from .src.record_sales import record_sales
from .src.record_cancellation import record_cancellation
from .src.record_refund import record_refund

app = FastAPI()


@app.get("/healthcheck")
def healthcheck():
    return {"status": "ok"}


@app.post("/slack")
async def slack_command(request: Request):
    form = await request.form()
    command = form.get("command", "")
    text = form.get("text", "")
    response_text = handle_slash(command, text)
    return PlainTextResponse(response_text)


@app.post("/shopify/order_created")
async def shopify_order_created(payload: dict):
    items = payload.get("items", [])
    if items:
        record_presales(items)
    record_sales(payload)
    return {"status": "processed"}


@app.post("/webhooks/orders_updated")
async def shopify_orders_updated(payload: dict):
    items = payload.get("items", []) or payload.get("line_items", [])
    if items:
        record_presales(items)
    record_sales(payload)
    return {"status": "processed"}


@app.post("/webhooks/orders_cancelled")
async def shopify_orders_cancelled(payload: dict):
    record_cancellation(payload)
    return {"status": "processed"}


@app.post("/webhooks/refunds_create")
async def shopify_refunds_create(payload: dict):
    record_refund(payload)
    return {"status": "processed"}


@app.post("/webhooks/orders_create")
async def orders_create_webhook(request: Request, background_tasks: BackgroundTasks):
    print("✅ Webhook received at /webhooks/orders_create")
    data = await request.json()
    background_tasks.add_task(process_order_data, data)
    return JSONResponse(content={"status": "success"})

def process_order_data(data):
    # This will execute after the response has been sent
    print("Received order:", data)
    # Placeholder for future DB or processing logic