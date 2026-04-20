
import pytest
from fastapi.testclient import TestClient


class FakeSender:
    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.sent: list[dict] = []

    def send(self, payload: dict) -> None:
        if self.raises is not None:
            raise self.raises
        self.sent.append(payload)


@pytest.fixture
def worker_module(monkeypatch, tmp_path):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("DISCORD_DELETION_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("DISCORD_OUTPUT_PATH", str(tmp_path / "discord.txt"))

    import importlib

    import worker.main as worker_main
    importlib.reload(worker_main)
    return worker_main


def test_health(worker_module):
    client = TestClient(worker_module.app)
    res = client.get("/health")
    assert res.status_code == 200


def test_page_created_sends_once(worker_module):
    default = FakeSender()
    worker_module.default_sender = default
    worker_module.deletion_sender = None

    client = TestClient(worker_module.app)
    body = {"type": "page.created", "id": "x"}
    res = client.post("/tasks/notion-event", json=body)
    assert res.status_code == 200
    assert len(default.sent) == 1
    assert "content" in default.sent[0]


def test_page_deleted_also_sends_to_deletion_sender(worker_module):
    default = FakeSender()
    deletion = FakeSender()
    worker_module.default_sender = default
    worker_module.deletion_sender = deletion

    client = TestClient(worker_module.app)
    body = {"type": "page.deleted", "id": "x"}
    res = client.post("/tasks/notion-event", json=body)
    assert res.status_code == 200
    assert len(default.sent) == 1
    assert len(deletion.sent) == 1


def test_page_created_does_not_trigger_deletion_sender(worker_module):
    default = FakeSender()
    deletion = FakeSender()
    worker_module.default_sender = default
    worker_module.deletion_sender = deletion

    client = TestClient(worker_module.app)
    body = {"type": "page.created", "id": "x"}
    client.post("/tasks/notion-event", json=body)
    assert len(deletion.sent) == 0


def test_invalid_json_returns_400(worker_module):
    client = TestClient(worker_module.app)
    res = client.post(
        "/tasks/notion-event",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 400


def test_send_failure_returns_503(worker_module):
    default = FakeSender(raises=RuntimeError("boom"))
    worker_module.default_sender = default

    client = TestClient(worker_module.app, raise_server_exceptions=False)
    body = {"type": "page.created", "id": "x"}
    res = client.post("/tasks/notion-event", json=body)
    assert res.status_code == 503
