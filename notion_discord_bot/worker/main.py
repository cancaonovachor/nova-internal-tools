import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from common.discord_format import format_event
from common.discord_sender import DiscordSender, FileDiscordSender, WebhookDiscordSender
from common.notion_client import NotionClient, enrich_event

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("notion_discord_bot.worker")

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_OUTPUT_PATH = Path(os.getenv("DISCORD_OUTPUT_PATH", "discord.txt"))


def _build_discord_sender() -> DiscordSender:
    if DISCORD_WEBHOOK_URL:
        logger.info("using WebhookDiscordSender")
        return WebhookDiscordSender(webhook_url=DISCORD_WEBHOOK_URL)
    logger.info("using FileDiscordSender path=%s", DISCORD_OUTPUT_PATH)
    return FileDiscordSender(output_path=DISCORD_OUTPUT_PATH)


app = FastAPI(title="notion-discord-bot worker")
notion_client = NotionClient(api_key=NOTION_API_KEY) if NOTION_API_KEY else None
discord_sender: DiscordSender = _build_discord_sender()


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/tasks/notion-event")
async def handle_notion_event(request: Request) -> dict:
    raw = await request.body()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    if notion_client is None:
        enriched = {"event": payload, "enriched": False}
    else:
        try:
            enriched = enrich_event(payload, notion_client)
        except Exception:
            logger.exception("enrichment crashed; sending raw event")
            enriched = {"event": payload, "enriched": False}

    message = format_event(enriched)
    try:
        discord_sender.send(message)
    except Exception as e:
        # 5xx を返して Cloud Tasks のリトライに乗せる
        logger.exception("discord send failed")
        raise HTTPException(status_code=503, detail=f"discord send failed: {e}")

    return {"status": "ok"}
