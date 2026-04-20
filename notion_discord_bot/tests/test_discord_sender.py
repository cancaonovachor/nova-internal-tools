from unittest.mock import MagicMock, patch

import pytest
import requests

from common.discord_sender import (
    FileDiscordSender,
    WebhookDiscordSender,
    render_payload_as_text,
)


def test_render_content_only():
    assert render_payload_as_text({"content": "hello"}) == "hello"


def test_render_embed_fields():
    text = render_payload_as_text(
        {
            "content": "c",
            "embeds": [
                {
                    "title": "T",
                    "description": "D",
                    "fields": [{"name": "n", "value": "v"}],
                }
            ],
        }
    )
    assert "c" in text
    assert "[embed title] T" in text
    assert "[embed] D" in text
    assert "[embed field] n: v" in text


def test_render_empty_payload_falls_back_to_json():
    assert render_payload_as_text({}) == "{}"


def test_file_sender_appends(tmp_path):
    out = tmp_path / "d" / "out.txt"
    s = FileDiscordSender(out)
    s.send({"content": "one"})
    s.send({"content": "two"})
    text = out.read_text(encoding="utf-8")
    assert "one" in text
    assert "two" in text


def test_webhook_sender_success():
    with patch("common.discord_sender.requests.post") as post:
        resp = MagicMock()
        resp.status_code = 204
        post.return_value = resp
        WebhookDiscordSender("https://example.com/webhook").send({"content": "x"})
    post.assert_called_once()


def test_webhook_sender_retries_on_5xx():
    with (
        patch("common.discord_sender.requests.post") as post,
        patch("common.discord_sender.time.sleep") as sleep,
    ):
        fail = MagicMock(status_code=500)
        fail.raise_for_status.side_effect = requests.HTTPError()
        ok = MagicMock(status_code=204)
        post.side_effect = [fail, fail, ok]
        WebhookDiscordSender("https://example.com/webhook").send({"content": "x"})
        assert post.call_count == 3
        assert sleep.call_count == 2


def test_webhook_sender_raises_after_max_retries():
    with (
        patch("common.discord_sender.requests.post") as post,
        patch("common.discord_sender.time.sleep"),
    ):
        fail = MagicMock(status_code=500)
        fail.raise_for_status.side_effect = requests.HTTPError()
        post.return_value = fail
        with pytest.raises(requests.HTTPError):
            WebhookDiscordSender("https://example.com/webhook").send({"content": "x"})


def test_webhook_sender_respects_retry_after_header():
    with (
        patch("common.discord_sender.requests.post") as post,
        patch("common.discord_sender.time.sleep") as sleep,
    ):
        limited = MagicMock(status_code=429)
        limited.headers = {"Retry-After": "2"}
        limited.raise_for_status.side_effect = requests.HTTPError()
        ok = MagicMock(status_code=204)
        post.side_effect = [limited, ok]
        WebhookDiscordSender("https://example.com/webhook").send({"content": "x"})
        sleep.assert_called_once_with(2.0)
