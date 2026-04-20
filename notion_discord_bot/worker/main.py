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
DISCORD_DELETION_WEBHOOK_URL = os.getenv("DISCORD_DELETION_WEBHOOK_URL")
DISCORD_OUTPUT_PATH = Path(os.getenv("DISCORD_OUTPUT_PATH", "discord.txt"))
# Cloud Tasks の retry_count がこの値未満のうちは失敗を warning 扱いにし、
# Error Reporting への通知を抑止する。queue の max_attempts=5 に対し既定値 4 で、
# 最後の 1 試行で失敗した場合だけ traceback 付き ERROR を残す。
CLOUD_TASKS_ERROR_RETRY_THRESHOLD = int(
    os.getenv("CLOUD_TASKS_ERROR_RETRY_THRESHOLD", "4")
)


def _build_default_sender() -> DiscordSender:
    if DISCORD_WEBHOOK_URL:
        logger.info("default sender: WebhookDiscordSender")
        return WebhookDiscordSender(webhook_url=DISCORD_WEBHOOK_URL)
    logger.info("default sender: FileDiscordSender path=%s", DISCORD_OUTPUT_PATH)
    return FileDiscordSender(output_path=DISCORD_OUTPUT_PATH)


def _build_deletion_sender() -> DiscordSender | None:
    if DISCORD_DELETION_WEBHOOK_URL:
        logger.info("deletion-only sender: WebhookDiscordSender (second webhook)")
        return WebhookDiscordSender(webhook_url=DISCORD_DELETION_WEBHOOK_URL)
    return None


app = FastAPI(title="notion-discord-bot worker")
notion_client = NotionClient(api_key=NOTION_API_KEY) if NOTION_API_KEY else None
default_sender: DiscordSender = _build_default_sender()
deletion_sender: DiscordSender | None = _build_deletion_sender()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tasks/notion-event")
async def handle_notion_event(request: Request) -> dict:
    raw = await request.body()
    try:
        webhook_payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    retry_count = int(request.headers.get("X-CloudTasks-TaskRetryCount", "0"))

    event_type = (
        webhook_payload.get("type") if isinstance(webhook_payload, dict) else None
    )

    if notion_client is None:
        enriched = {"event": webhook_payload, "enriched": False}
    else:
        try:
            enriched = enrich_event(webhook_payload, notion_client)
        except Exception:
            logger.exception("enrichment crashed; sending raw event")
            enriched = {"event": webhook_payload, "enriched": False}

    discord_payload = format_event(enriched)

    try:
        default_sender.send(discord_payload)
        if event_type == "page.deleted" and deletion_sender is not None:
            deletion_sender.send(discord_payload)
    except Exception as e:
        # 5xx を返して Cloud Tasks のリトライに乗せる
        if retry_count < CLOUD_TASKS_ERROR_RETRY_THRESHOLD:
            logger.warning(
                "discord send failed (retry=%d, Cloud Tasks will retry): %s",
                retry_count,
                e,
            )
        else:
            logger.exception(
                "discord send failed repeatedly (retry=%d)", retry_count
            )
        raise HTTPException(status_code=503, detail=f"discord send failed: {e}")

    return {"status": "ok"}
