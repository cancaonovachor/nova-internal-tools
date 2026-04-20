import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
DEFAULT_TIMEOUT = 15


class NotionClient:
    def __init__(self, api_key: str, notion_version: str = NOTION_VERSION) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": notion_version,
            }
        )
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def get_page(self, page_id: str) -> dict[str, Any]:
        r = self._session.get(f"{BASE_URL}/pages/{page_id}", timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def get_user(self, user_id: str) -> dict[str, Any]:
        r = self._session.get(f"{BASE_URL}/users/{user_id}", timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r.json()

    def get_block(self, block_id: str) -> dict[str, Any]:
        r = self._session.get(f"{BASE_URL}/blocks/{block_id}", timeout=DEFAULT_TIMEOUT)
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
    # paragraph / heading / bulleted_list_item など大半のブロック
    rich = content.get("rich_text")
    if isinstance(rich, list):
        return "".join(r.get("plain_text", "") for r in rich)
    # child_page / child_database はタイトルが title フィールドに入る
    title = content.get("title")
    if isinstance(title, str):
        return title
    return ""


def extract_property_value(prop: dict[str, Any]) -> str:
    """Notion property object を人間可読な文字列に変換する。"""
    ptype = prop.get("type")
    if not ptype:
        return ""
    content = prop.get(ptype)
    if content is None:
        return ""

    if ptype in ("title", "rich_text"):
        if isinstance(content, list):
            return "".join(r.get("plain_text", "") for r in content)

    if ptype == "number":
        return "" if content is None else str(content)

    if ptype in ("select", "status"):
        if isinstance(content, dict):
            return content.get("name") or ""

    if ptype == "multi_select":
        if isinstance(content, list):
            return ", ".join(o.get("name", "") for o in content if isinstance(o, dict))

    if ptype == "date":
        if isinstance(content, dict):
            start = content.get("start") or ""
            end = content.get("end")
            return f"{start} → {end}" if end else start

    if ptype == "people":
        if isinstance(content, list):
            return ", ".join(
                p.get("name", "") for p in content if isinstance(p, dict)
            )

    if ptype == "checkbox":
        return "true" if content else "false"

    if ptype in ("url", "email", "phone_number"):
        return str(content) if content else ""

    if ptype in ("created_by", "last_edited_by"):
        if isinstance(content, dict):
            return content.get("name") or ""

    if ptype in ("created_time", "last_edited_time"):
        return str(content) if content else ""

    if ptype == "files":
        if isinstance(content, list):
            return ", ".join(f.get("name", "") for f in content if isinstance(f, dict))

    if ptype == "relation":
        if isinstance(content, list):
            return f"{len(content)} 件"

    if ptype == "formula":
        if isinstance(content, dict):
            ftype = content.get("type")
            if ftype and ftype in content:
                return str(content.get(ftype, "") or "")

    if ptype == "rollup":
        if isinstance(content, dict):
            rtype = content.get("type")
            if rtype and rtype in content:
                inner = content.get(rtype)
                if isinstance(inner, list):
                    return ", ".join(str(x) for x in inner)
                return str(inner) if inner is not None else ""

    if ptype == "unique_id":
        if isinstance(content, dict):
            num = content.get("number")
            prefix = content.get("prefix")
            return f"{prefix}-{num}" if prefix and num is not None else str(num or "")

    # フォールバック
    return str(content)


def enrich_event(event: dict[str, Any], client: NotionClient) -> dict[str, Any]:
    """Notion webhook payload に page/author/block/property の情報を付与する。"""
    enriched: dict[str, Any] = {"event": event}

    entity = event.get("entity") or {}
    page_id = entity.get("id") if entity.get("type") == "page" else None
    page: dict[str, Any] | None = None

    if page_id:
        try:
            page = client.get_page(page_id)
            enriched["page_title"] = extract_page_title(page)
            enriched["page_url"] = page.get("url")
        except requests.RequestException as e:
            logger.warning("failed to fetch page %s: %s", page_id, e)

    author_names: list[str | None] = []
    for a in event.get("authors") or []:
        uid = a.get("id")
        if not uid:
            continue
        try:
            u = client.get_user(uid)
            author_names.append(u.get("name"))
        except requests.RequestException as e:
            logger.warning("failed to fetch user %s: %s", uid, e)
    enriched["authors"] = author_names

    data = event.get("data") or {}

    # 本文ブロックの変更
    updated_blocks = []
    for b in data.get("updated_blocks") or []:
        bid = b.get("id")
        if not bid:
            continue
        try:
            blk = client.get_block(bid)
            updated_blocks.append(
                {
                    "id": bid,
                    "type": blk.get("type"),
                    "text": extract_block_text(blk),
                }
            )
        except requests.RequestException as e:
            logger.warning("failed to fetch block %s: %s", bid, e)
    enriched["updated_blocks"] = updated_blocks

    # プロパティの変更 — webhook は更新プロパティ ID のみ返すので、
    # 取得済みのページ properties から name/value を引く
    updated_property_ids: list[str] = []
    raw_updated = data.get("updated_properties") or []
    for item in raw_updated:
        if isinstance(item, dict):
            pid = item.get("id")
        else:
            pid = item
        if pid:
            updated_property_ids.append(pid)

    updated_properties: list[dict[str, str]] = []
    if updated_property_ids and page is not None:
        page_props = page.get("properties") or {}
        id_to_name_prop = {
            prop.get("id"): (name, prop)
            for name, prop in page_props.items()
            if isinstance(prop, dict) and prop.get("id")
        }
        for pid in updated_property_ids:
            if pid in id_to_name_prop:
                name, prop = id_to_name_prop[pid]
                updated_properties.append(
                    {"name": name, "value": extract_property_value(prop)}
                )
            else:
                updated_properties.append({"name": pid, "value": ""})
    enriched["updated_properties"] = updated_properties

    return enriched
