import base64
import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from common.discord_sender import create_sender
from common.formatter import format_pubsub_message


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("gcp_alert_discord_bot")

app = FastAPI(title="gcp-alert-discord-bot")
sender = create_sender()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/pubsub/push")
async def pubsub_push(request: Request) -> dict:
    raw = await request.body()
    try:
        envelope = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    message = envelope.get("message") if isinstance(envelope, dict) else None
    if not isinstance(message, dict):
        logger.warning("missing message in envelope: %s", envelope)
        # Pub/Sub は 2xx を返さないと無限リトライされる。壊れたメッセージは ack する。
        return {"status": "ignored", "reason": "no message"}

    data_b64 = message.get("data")
    attrs = message.get("attributes") or {}
    if not data_b64:
        logger.info("empty data; attrs=%s", attrs)
        return {"status": "ignored", "reason": "empty data"}

    try:
        data_bytes = base64.b64decode(data_b64)
    except Exception:
        logger.exception("failed to base64-decode data")
        return {"status": "ignored", "reason": "bad base64"}

    try:
        body = json.loads(data_bytes)
    except json.JSONDecodeError:
        body = {"_raw": data_bytes.decode("utf-8", errors="replace")}

    if not isinstance(body, dict):
        body = {"_value": body}

    try:
        content = format_pubsub_message(body, attrs)
    except Exception:
        logger.exception("formatter failed; body=%s", body)
        # フォーマットに失敗しても送信は試みる (unknown fallback)
        from common.formatter import format_unknown

        content = format_unknown(body)

    try:
        sender.send({"content": content})
    except Exception:
        logger.exception("discord send failed")
        # Pub/Sub にリトライさせる
        raise HTTPException(status_code=500, detail="discord send failed")

    return {"status": "ok"}
