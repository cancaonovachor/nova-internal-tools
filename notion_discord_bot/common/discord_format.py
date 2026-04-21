from typing import Any

EVENT_ACTION = {
    "page.created": "を作成",
    "page.content_updated": "の本文を編集",
    "page.properties_updated": "を編集",
    "page.deleted": "を削除",
    "page.undeleted": "を復元",
    "page.locked": "をロック",
    "page.unlocked": "をロック解除",
    "page.moved": "を移動",
    "comment.created": "にコメント",
    "comment.updated": "のコメントを編集",
    "comment.deleted": "のコメントを削除",
    "database.created": "を作成 (DB)",
    "database.content_updated": "を更新 (DB)",
    "database.schema_updated": "のスキーマを変更",
}

# Discord embed の制限
_FIELD_VALUE_LIMIT = 1024
_MAX_FIELDS_PER_EMBED = 25


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_event(enriched: dict[str, Any]) -> dict[str, Any]:
    """enriched event を Discord webhook payload (content + embeds) に整形する。"""
    event = enriched.get("event") or {}
    event_type = event.get("type", "unknown")
    action = EVENT_ACTION.get(event_type, event_type)

    title = (enriched.get("page_title") or "").strip() or "(無題)"
    url = enriched.get("page_url")
    authors = [a for a in (enriched.get("authors") or []) if a] or ["unknown"]
    author_str = ", ".join(authors)

    if url:
        header = f"**{author_str}** が **[{title}]({url})** {action}"
    else:
        header = f"**{author_str}** が **{title}** {action}"

    fields: list[dict[str, Any]] = []

    # プロパティ更新
    for p in enriched.get("updated_properties") or []:
        name = p.get("name") or "property"
        value = p.get("value") or "(空)"
        fields.append(
            {
                "name": name[:256],
                "value": _truncate(value, _FIELD_VALUE_LIMIT),
                "inline": False,
            }
        )

    # 本文ブロック更新
    for b in enriched.get("updated_blocks") or []:
        text = (b.get("text") or "").strip()
        btype = b.get("type") or "block"
        display = text or "(空)"
        fields.append(
            {
                "name": btype[:256],
                "value": _truncate(display, _FIELD_VALUE_LIMIT),
                "inline": False,
            }
        )

    payload: dict[str, Any] = {"content": header}
    if fields:
        payload["embeds"] = [{"fields": fields[:_MAX_FIELDS_PER_EMBED]}]
    return payload
