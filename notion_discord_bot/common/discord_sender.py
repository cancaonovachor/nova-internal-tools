import json
import logging
import time
from pathlib import Path
from typing import Any, Protocol

import requests


logger = logging.getLogger(__name__)


class DiscordSender(Protocol):
    def send(self, payload: dict[str, Any]) -> None: ...


def render_payload_as_text(payload: dict[str, Any]) -> str:
    """Discord webhook payload をローカルログ用に人間可読な文字列へ変換する。"""
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
    """ローカル用スタブ。Discord webhook POST の代わりにファイルへ追記する。"""

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
    """本番用。Discord Incoming Webhook に POST する。

    429 は Retry-After を尊重して短時間リトライ、5xx は指数バックオフでリトライ。
    リトライを使い切っても失敗する場合のみ例外を投げ、Cloud Tasks のリトライに委ねる。
    """

    _MAX_RETRIES = 3
    _MAX_SLEEP_SECONDS = 10.0

    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout

    def _retry_after_seconds(self, response: requests.Response) -> float:
        header = response.headers.get("Retry-After")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        try:
            body = response.json()
            if isinstance(body, dict) and "retry_after" in body:
                return float(body["retry_after"])
        except ValueError:
            pass
        return 1.0

    def send(self, payload: dict[str, Any]) -> None:
        logger.info("discord payload:\n%s", render_payload_as_text(payload))
        for attempt in range(1, self._MAX_RETRIES + 1):
            r = requests.post(
                self._webhook_url,
                json=payload,
                timeout=self._timeout,
            )
            if r.status_code < 400:
                return
            if r.status_code == 429 or 500 <= r.status_code < 600:
                if attempt >= self._MAX_RETRIES:
                    r.raise_for_status()
                if r.status_code == 429:
                    sleep_for = min(self._retry_after_seconds(r), self._MAX_SLEEP_SECONDS)
                else:
                    sleep_for = min(0.5 * (2 ** (attempt - 1)), self._MAX_SLEEP_SECONDS)
                logger.warning(
                    "discord webhook %d, sleeping %.2fs (attempt %d/%d)",
                    r.status_code,
                    sleep_for,
                    attempt,
                    self._MAX_RETRIES,
                )
                time.sleep(sleep_for)
                continue
            r.raise_for_status()
