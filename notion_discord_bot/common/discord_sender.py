import logging
from pathlib import Path
from typing import Protocol

import requests


logger = logging.getLogger(__name__)


class DiscordSender(Protocol):
    def send(self, message: str) -> None: ...


class FileDiscordSender:
    """Phase 1 / ローカル用スタブ。Discord webhook POST の代わりにファイルへ追記する。"""

    _SEPARATOR = "\n\n---\n\n"

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path

    def send(self, message: str) -> None:
        logger.info("discord message:\n%s", message)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._output_path.open("a", encoding="utf-8") as f:
            f.write(message)
            f.write(self._SEPARATOR)


class WebhookDiscordSender:
    """本番用。Discord Incoming Webhook に POST する。

    429/5xx は例外として上げ、呼び出し側（worker）がエラーレスポンスを返すことで
    Cloud Tasks のリトライに委ねる。
    """

    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout

    def send(self, message: str) -> None:
        r = requests.post(
            self._webhook_url,
            json={"content": message},
            timeout=self._timeout,
        )
        r.raise_for_status()
