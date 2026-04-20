import json
import logging
from pathlib import Path
from typing import Any, Protocol

import requests


logger = logging.getLogger(__name__)


class DiscordSender(Protocol):
    def send(self, payload: dict[str, Any]) -> None: ...


def render_payload_as_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    content = payload.get("content")
    if content:
        lines.append(str(content))
    for embed in payload.get("embeds") or []:
        if embed.get("title"):
            lines.append(f"[embed title] {embed['title']}")
        if embed.get("description"):
            lines.append(f"[embed] {embed['description']}")
        for field in embed.get("fields") or []:
            name = field.get("name", "")
            value = field.get("value", "")
            lines.append(f"[embed field] {name}: {value}")
    return "\n".join(lines) if lines else json.dumps(payload, ensure_ascii=False)


class FileDiscordSender:
    _SEPARATOR = "\n\n---\n\n"

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path

    def send(self, payload: dict[str, Any]) -> None:
        text = render_payload_as_text(payload)
        logger.info("discord payload (text view):\n%s", text)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._output_path.open("a", encoding="utf-8") as f:
            f.write(text)
            f.write(self._SEPARATOR)


class WebhookDiscordSender:
    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout

    def send(self, payload: dict[str, Any]) -> None:
        logger.info("discord payload:\n%s", render_payload_as_text(payload))
        r = requests.post(self._webhook_url, json=payload, timeout=self._timeout)
        r.raise_for_status()


def create_sender() -> DiscordSender:
    import os

    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if url:
        return WebhookDiscordSender(url)
    log_path = Path(os.getenv("DISCORD_LOG_FILE", "./discord.txt"))
    return FileDiscordSender(log_path)
