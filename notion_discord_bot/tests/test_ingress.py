import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def ingress_module(monkeypatch, tmp_path):
    # Ensure deterministic env before module import
    monkeypatch.setenv("NOTION_VERIFICATION_TOKEN", "test-token")
    monkeypatch.setenv(
        "NOTION_ALLOWED_EVENTS",
        "page.created,page.content_updated,page.deleted",
    )
    monkeypatch.setenv("WORKER_URL", "http://worker.local/tasks/notion-event")
    monkeypatch.delenv("CLOUD_TASKS_QUEUE", raising=False)

    # Fresh import so module-level env reads use our patched env
    import importlib

    import ingress.main as ingress_main
    importlib.reload(ingress_main)
    return ingress_main


class FakeEnqueuer:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, str | None]] = []

    def enqueue(self, payload, task_id=None):
        self.calls.append((payload, task_id))


def _sign(body: bytes, token: str) -> str:
    return "sha256=" + hmac.new(token.encode(), body, hashlib.sha256).hexdigest()


def test_health(ingress_module):
    client = TestClient(ingress_module.app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_verification_token_echoed(ingress_module):
    client = TestClient(ingress_module.app)
    res = client.post("/webhook/notion", json={"verification_token": "abc"})
    assert res.status_code == 200
    assert res.json()["status"] == "verification_received"


def test_signature_rejection(ingress_module):
    client = TestClient(ingress_module.app)
    body = json.dumps({"type": "page.created", "id": "evt-1"}).encode()
    res = client.post(
        "/webhook/notion",
        content=body,
        headers={
            "content-type": "application/json",
            "x-notion-signature": "sha256=deadbeef",
        },
    )
    assert res.status_code == 401


def test_accepted_event_is_enqueued(ingress_module):
    fake = FakeEnqueuer()
    ingress_module.enqueuer = fake

    client = TestClient(ingress_module.app)
    body = json.dumps({"type": "page.created", "id": "evt-1"}).encode()
    res = client.post(
        "/webhook/notion",
        content=body,
        headers={
            "content-type": "application/json",
            "x-notion-signature": _sign(body, "test-token"),
        },
    )
    assert res.status_code == 200
    j = res.json()
    assert j["status"] == "accepted"
    assert j["task_id"] == "notion-evt-1"
    # BackgroundTasks runs after response; TestClient waits for it
    assert len(fake.calls) == 1
    payload, task_id = fake.calls[0]
    assert payload["type"] == "page.created"
    assert task_id == "notion-evt-1"


def test_filtered_event_not_enqueued(ingress_module):
    fake = FakeEnqueuer()
    ingress_module.enqueuer = fake

    client = TestClient(ingress_module.app)
    body = json.dumps({"type": "database.schema_updated", "id": "evt-2"}).encode()
    res = client.post(
        "/webhook/notion",
        content=body,
        headers={
            "content-type": "application/json",
            "x-notion-signature": _sign(body, "test-token"),
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "filtered"
    assert fake.calls == []


def test_invalid_json_returns_400(ingress_module):
    client = TestClient(ingress_module.app)
    res = client.post(
        "/webhook/notion",
        content=b"not-json",
        headers={
            "content-type": "application/json",
            "x-notion-signature": "sha256=whatever",
        },
    )
    assert res.status_code == 400


def test_missing_event_id_no_task_name(ingress_module):
    fake = FakeEnqueuer()
    ingress_module.enqueuer = fake

    client = TestClient(ingress_module.app)
    body = json.dumps({"type": "page.created"}).encode()
    res = client.post(
        "/webhook/notion",
        content=body,
        headers={
            "content-type": "application/json",
            "x-notion-signature": _sign(body, "test-token"),
        },
    )
    assert res.status_code == 200
    assert res.json()["task_id"] is None
    assert fake.calls[0][1] is None
