import json
import logging
import os
from typing import Any, Protocol

import requests

logger = logging.getLogger(__name__)


class TaskEnqueuer(Protocol):
    def enqueue(self, payload: dict[str, Any], task_id: str | None = None) -> None: ...


class HTTPDirectEnqueuer:
    """ローカル開発用。Cloud Tasks を使わず worker に直接 HTTP POST する。"""

    def __init__(self, worker_url: str, timeout: float = 10.0) -> None:
        self._worker_url = worker_url
        self._timeout = timeout

    def enqueue(self, payload: dict[str, Any], task_id: str | None = None) -> None:
        headers = {"Content-Type": "application/json"}
        if task_id:
            headers["X-Task-Id"] = task_id
        r = requests.post(
            self._worker_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            timeout=self._timeout,
        )
        r.raise_for_status()


class CloudTasksEnqueuer:
    """本番用。Cloud Tasks queue に HTTP ターゲットのタスクを投入する。"""

    def __init__(
        self,
        project: str,
        location: str,
        queue: str,
        worker_url: str,
        service_account_email: str | None = None,
    ) -> None:
        from google.cloud import tasks_v2

        self._tasks_v2 = tasks_v2
        self._client = tasks_v2.CloudTasksClient()
        self._parent = self._client.queue_path(project, location, queue)
        self._worker_url = worker_url
        self._service_account_email = service_account_email

    def enqueue(self, payload: dict[str, Any], task_id: str | None = None) -> None:
        from google.api_core.exceptions import AlreadyExists

        task: dict[str, Any] = {
            "http_request": {
                "http_method": self._tasks_v2.HttpMethod.POST,
                "url": self._worker_url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode("utf-8"),
            }
        }
        if self._service_account_email:
            task["http_request"]["oidc_token"] = {
                "service_account_email": self._service_account_email,
                "audience": self._worker_url,
            }
        if task_id:
            task["name"] = f"{self._parent}/tasks/{task_id}"
        try:
            self._client.create_task(parent=self._parent, task=task)
        except AlreadyExists:
            # 同じ task name のタスクが既にキューにある（or 最近処理された）→ dedup 成立。
            logger.info("task %s already exists; deduplicated", task_id)


def create_enqueuer() -> TaskEnqueuer:
    """環境変数に応じて Enqueuer を生成する。

    CLOUD_TASKS_QUEUE が設定されていれば CloudTasksEnqueuer を返す。
    それ以外はローカル開発想定で HTTPDirectEnqueuer を返す。
    """
    queue = os.getenv("CLOUD_TASKS_QUEUE")
    worker_url = os.getenv(
        "WORKER_URL", "http://localhost:8081/tasks/notion-event"
    )
    if queue:
        project = os.environ["GOOGLE_CLOUD_PROJECT"]
        location = os.environ["CLOUD_TASKS_LOCATION"]
        sa = os.getenv("WORKER_INVOKER_SA")
        logger.info(
            "using CloudTasksEnqueuer queue=%s location=%s worker_url=%s",
            queue,
            location,
            worker_url,
        )
        return CloudTasksEnqueuer(project, location, queue, worker_url, sa)
    logger.info("using HTTPDirectEnqueuer worker_url=%s", worker_url)
    return HTTPDirectEnqueuer(worker_url)
