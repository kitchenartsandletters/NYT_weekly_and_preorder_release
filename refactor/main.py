from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from .slack.slack_handler import handle_slash
from .src.record_presales import record_presales

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
    return {"status": "processed"}
