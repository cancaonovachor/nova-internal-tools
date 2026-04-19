import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from common.discord_format import format_event
from common.discord_sender import FileDiscordSender
from common.signature import verify_notion_signature
from receiver.notion_client import NotionClient, enrich_event
from receiver.publisher import StdoutLogPublisher

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("notion_discord_bot.receiver")

LOG_PATH = Path(os.getenv("EVENT_LOG_PATH", "log.txt"))
DISCORD_OUTPUT_PATH = Path(os.getenv("DISCORD_OUTPUT_PATH", "discord.txt"))
VERIFICATION_TOKEN = os.getenv("NOTION_VERIFICATION_TOKEN")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")

app = FastAPI(title="notion-discord-bot receiver")
publisher = StdoutLogPublisher(log_path=LOG_PATH)
discord_sender = FileDiscordSender(output_path=DISCORD_OUTPUT_PATH)
notion_client = NotionClient(api_key=NOTION_API_KEY) if NOTION_API_KEY else None


def _enrich_and_publish(payload: dict) -> None:
    if notion_client is None:
        enriched = {"event": payload, "enriched": False}
    else:
        try:
            enriched = enrich_event(payload, notion_client)
        except Exception:
            logger.exception("enrichment crashed; publishing raw event")
            enriched = {"event": payload, "enriched": False}

    publisher.publish(enriched)
    try:
        discord_sender.send(format_event(enriched))
    except Exception:
        logger.exception("discord formatting/sending failed")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/webhook/notion")
async def notion_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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

    background_tasks.add_task(_enrich_and_publish, payload)
    return {"status": "accepted"}
