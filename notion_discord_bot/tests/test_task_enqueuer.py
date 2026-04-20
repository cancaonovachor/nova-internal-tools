import json
from unittest.mock import MagicMock, patch

import pytest

from common.task_enqueuer import (
    HTTPDirectEnqueuer,
    create_enqueuer,
)


def test_http_direct_enqueuer_posts_payload():
    with patch("common.task_enqueuer.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.raise_for_status = MagicMock()

        enq = HTTPDirectEnqueuer("http://worker.local/tasks/notion-event")
        enq.enqueue({"type": "page.created"}, task_id="notion-abc")

    post.assert_called_once()
    kwargs = post.call_args.kwargs
    assert kwargs["data"] == json.dumps({"type": "page.created"}).encode()
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["headers"]["X-Task-Id"] == "notion-abc"


def test_http_direct_enqueuer_omits_task_id_header_when_none():
    with patch("common.task_enqueuer.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.raise_for_status = MagicMock()

        HTTPDirectEnqueuer("http://worker/").enqueue({"a": 1}, task_id=None)
    assert "X-Task-Id" not in post.call_args.kwargs["headers"]


def test_create_enqueuer_http_direct_when_queue_unset(monkeypatch):
    monkeypatch.delenv("CLOUD_TASKS_QUEUE", raising=False)
    monkeypatch.setenv("WORKER_URL", "http://local:8081/x")
    enq = create_enqueuer()
    assert isinstance(enq, HTTPDirectEnqueuer)


def test_create_enqueuer_requires_project_when_cloud_tasks(monkeypatch):
    monkeypatch.setenv("CLOUD_TASKS_QUEUE", "myqueue")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(KeyError):
        create_enqueuer()
