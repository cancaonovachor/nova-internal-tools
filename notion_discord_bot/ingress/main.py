import json
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

from common.signature import verify_notion_signature
from common.task_enqueuer import create_enqueuer

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("notion_discord_bot.ingress")

VERIFICATION_TOKEN = os.getenv("NOTION_VERIFICATION_TOKEN")
ALLOWED_EVENTS = {
    e.strip()
    for e in os.getenv(
        "NOTION_ALLOWED_EVENTS",
        "page.created,page.content_updated,page.properties_updated,page.deleted,comment.created",
    ).split(",")
    if e.strip()
}

app = FastAPI(title="notion-discord-bot ingress")
enqueuer = create_enqueuer()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/notion")
async def notion_webhook(
    request: Request,
    x_notion_signature: str | None = Header(default=None),
) -> dict:
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    if isinstance(payload, dict) and "verification_token" in payload:
        token = payload["verification_token"]
        logger.warning("Notion verification_token received: %s", token)
        return {"status": "verification_received"}

    if VERIFICATION_TOKEN:
        if not verify_notion_signature(
            raw_body=raw_body,
            signature_header=x_notion_signature,
            verification_token=VERIFICATION_TOKEN,
        ):
            logger.warning("signature verification failed")
            raise HTTPException(status_code=401, detail="invalid signature")
    else:
        logger.warning(
            "NOTION_VERIFICATION_TOKEN is not set; skipping signature verification"
        )

    event_type = payload.get("type") if isinstance(payload, dict) else None
    if event_type not in ALLOWED_EVENTS:
        logger.info("filtered event_type=%s", event_type)
        return {"status": "filtered", "event_type": event_type}

    event_id = payload.get("id") if isinstance(payload, dict) else None
    task_id = f"notion-{event_id}" if event_id else None

    # Cloud Run の CPU throttling 有効下では response 返却後に CPU が絞られて
    # BackgroundTask が詰まりうるため、enqueue は同期で実行する。
    try:
        enqueuer.enqueue(payload, task_id)
    except Exception:
        logger.exception("enqueue failed (task_id=%s)", task_id)
        raise HTTPException(status_code=503, detail="enqueue failed")

    return {"status": "accepted", "event_type": event_type, "task_id": task_id}
