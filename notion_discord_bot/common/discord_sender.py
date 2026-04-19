import logging
from pathlib import Path
from typing import Protocol


logger = logging.getLogger(__name__)


class DiscordSender(Protocol):
    def send(self, message: str) -> None: ...


class FileDiscordSender:
    """Phase 1 スタブ。Discord webhook POST の代わりに指定ファイルへ追記する。"""

    _SEPARATOR = "\n\n---\n\n"

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path

    def send(self, message: str) -> None:
        logger.info("discord message:\n%s", message)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._output_path.open("a", encoding="utf-8") as f:
            f.write(message)
            f.write(self._SEPARATOR)
