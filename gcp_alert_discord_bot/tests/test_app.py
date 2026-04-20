import base64
import json

import pytest
from fastapi.testclient import TestClient

import app.main as app_main


class FakeSender:
    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.sent: list[dict] = []

    def send(self, payload: dict) -> None:
        if self.raises is not None:
            raise self.raises
        self.sent.append(payload)


@pytest.fixture
def client_and_sender(monkeypatch):
    fake = FakeSender()
    monkeypatch.setattr(app_main, "sender", fake)
    return TestClient(app_main.app), fake


def _pubsub_envelope(body: dict, attrs: dict | None = None) -> dict:
    data = base64.b64encode(json.dumps(body).encode("utf-8")).decode("ascii")
    msg: dict = {"data": data}
    if attrs is not None:
        msg["attributes"] = attrs
    return {"message": msg}


def test_health(client_and_sender):
    client, _ = client_and_sender
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_pubsub_push_budget(client_and_sender):
    client, fake = client_and_sender
    body = {
        "budgetDisplayName": "monthly",
        "alertThresholdExceeded": 0.5,
        "costAmount": 500,
        "budgetAmount": 1000,
        "currencyCode": "JPY",
    }
    res = client.post("/pubsub/push", json=_pubsub_envelope(body))
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
    assert len(fake.sent) == 1
    assert "Budget" in fake.sent[0]["content"]


def test_pubsub_push_monitoring(client_and_sender):
    client, fake = client_and_sender
    body = {"incident": {"state": "OPEN", "policy_name": "p"}}
    res = client.post("/pubsub/push", json=_pubsub_envelope(body))
    assert res.status_code == 200
    assert len(fake.sent) == 1
    assert "Alert" in fake.sent[0]["content"]


def test_pubsub_push_missing_message_is_acked(client_and_sender):
    client, fake = client_and_sender
    res = client.post("/pubsub/push", json={})
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
    assert fake.sent == []


def test_pubsub_push_empty_data_is_acked(client_and_sender):
    client, fake = client_and_sender
    res = client.post("/pubsub/push", json={"message": {"attributes": {}}})
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
    assert fake.sent == []


def test_pubsub_push_invalid_base64_is_acked(client_and_sender):
    client, fake = client_and_sender
    res = client.post(
        "/pubsub/push",
        json={"message": {"data": "!!!not-base64!!!"}},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"
    assert fake.sent == []


def test_pubsub_push_invalid_json_body(client_and_sender):
    client, _ = client_and_sender
    res = client.post(
        "/pubsub/push",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 400


def test_pubsub_push_sender_failure_returns_500(monkeypatch):
    fake = FakeSender(raises=RuntimeError("boom"))
    monkeypatch.setattr(app_main, "sender", fake)
    client = TestClient(app_main.app, raise_server_exceptions=False)
    body = {"incident": {"state": "OPEN", "policy_name": "p"}}
    res = client.post("/pubsub/push", json=_pubsub_envelope(body))
    assert res.status_code == 500
