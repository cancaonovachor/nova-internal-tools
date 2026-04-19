import json
import logging
from pathlib import Path
from typing import Protocol


logger = logging.getLogger(__name__)


class Publisher(Protocol):
    def publish(self, payload: dict) -> None: ...


class StdoutLogPublisher:
    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path

    def publish(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        logger.info("publish: %s", line)
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
