import logging
from typing import Any

import requests


logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


class NotionClient:
    def __init__(self, api_key: str, notion_version: str = NOTION_VERSION) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": notion_version,
            }
        )

    def get_page(self, page_id: str) -> dict[str, Any]:
        r = self._session.get(f"{BASE_URL}/pages/{page_id}", timeout=10)
        r.raise_for_status()
        return r.json()

    def get_user(self, user_id: str) -> dict[str, Any]:
        r = self._session.get(f"{BASE_URL}/users/{user_id}", timeout=10)
        r.raise_for_status()
        return r.json()

    def get_block(self, block_id: str) -> dict[str, Any]:
        r = self._session.get(f"{BASE_URL}/blocks/{block_id}", timeout=10)
        r.raise_for_status()
        return r.json()


def extract_page_title(page: dict[str, Any]) -> str | None:
    props = page.get("properties", {}) or {}
    for prop in props.values():
        if prop.get("type") == "title":
            rich = prop.get("title", []) or []
            text = "".join(r.get("plain_text", "") for r in rich)
            return text or None
    return None


def extract_block_text(block: dict[str, Any]) -> str:
    btype = block.get("type")
    if not btype:
        return ""
    content = block.get(btype, {}) or {}
    rich = content.get("rich_text", []) or []
    return "".join(r.get("plain_text", "") for r in rich)


def enrich_event(event: dict[str, Any], client: NotionClient) -> dict[str, Any]:
    """Notion webhook payload に page title / author name / block text を付与する。"""
    enriched: dict[str, Any] = {"event": event}

    entity = event.get("entity") or {}
    if entity.get("type") == "page" and entity.get("id"):
        try:
            page = client.get_page(entity["id"])
            enriched["page_title"] = extract_page_title(page)
            enriched["page_url"] = page.get("url")
        except requests.HTTPError as e:
            logger.warning("failed to fetch page %s: %s", entity["id"], e)

    author_names: list[str | None] = []
    for a in event.get("authors") or []:
        uid = a.get("id")
        if not uid:
            continue
        try:
            u = client.get_user(uid)
            author_names.append(u.get("name"))
        except requests.HTTPError as e:
            logger.warning("failed to fetch user %s: %s", uid, e)
    enriched["authors"] = author_names

    updated = []
    for b in (event.get("data") or {}).get("updated_blocks") or []:
        bid = b.get("id")
        if not bid:
            continue
        try:
            blk = client.get_block(bid)
            updated.append(
                {
                    "id": bid,
                    "type": blk.get("type"),
                    "text": extract_block_text(blk),
                }
            )
        except requests.HTTPError as e:
            logger.warning("failed to fetch block %s: %s", bid, e)
    enriched["updated_blocks"] = updated

    return enriched
