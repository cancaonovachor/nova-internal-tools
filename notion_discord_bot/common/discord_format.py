from typing import Any


EVENT_ACTION = {
    "page.created": "作成",
    "page.content_updated": "本文更新",
    "page.properties_updated": "プロパティ更新",
    "page.deleted": "削除",
    "page.undeleted": "復元",
    "page.locked": "ロック",
    "page.unlocked": "ロック解除",
    "page.moved": "移動",
    "comment.created": "コメント追加",
    "comment.updated": "コメント更新",
    "comment.deleted": "コメント削除",
    "database.created": "データベース作成",
    "database.content_updated": "データベース更新",
    "database.schema_updated": "スキーマ更新",
}


def format_event(enriched: dict[str, Any]) -> str:
    """enriched event を Discord 向け markdown 文字列に整形する。"""
    event = enriched.get("event") or {}
    event_type = event.get("type", "unknown")
    action = EVENT_ACTION.get(event_type, event_type)

    title = enriched.get("page_title") or "(無題)"
    url = enriched.get("page_url")
    authors = [a for a in (enriched.get("authors") or []) if a] or ["unknown"]
    author_str = ", ".join(authors)

    if url:
        header = f"**[{title}]({url})** が{action}されました"
    else:
        header = f"**{title}** が{action}されました"

    lines = [
        f"`{event_type}`",
        header,
        f"by {author_str}",
    ]

    blocks = enriched.get("updated_blocks") or []
    if blocks:
        lines.append("")
        lines.append("**変更ブロック:**")
        for b in blocks:
            text = (b.get("text") or "").strip() or "(空)"
            btype = b.get("type") or "block"
            lines.append(f"- `{btype}`: {text}")

    return "\n".join(lines)
