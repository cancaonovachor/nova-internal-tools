from unittest.mock import MagicMock, patch

import requests

from common.discord import format_article_message, send_discord_message


def test_format_article_message_includes_all_fields():
    msg = format_article_message(
        title="Hello",
        summary="A summary",
        url="https://example.com/article",
        source="BlogX",
        date="2026-04-21",
    )
    assert "Hello" in msg
    assert "A summary" in msg
    assert "https://example.com/article" in msg
    assert "BlogX" in msg
    assert "2026-04-21" in msg


def test_send_discord_message_uses_webhook_arg():
    with patch("common.discord.requests.post") as post:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        post.return_value = resp
        ok = send_discord_message("hi", webhook_url="https://example.com/webhook")
        assert ok is True
        post.assert_called_once_with(
            "https://example.com/webhook", json={"content": "hi"}
        )


def test_send_discord_message_reads_env(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/from-env")
    with patch("common.discord.requests.post") as post:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        post.return_value = resp
        assert send_discord_message("hi") is True
        assert post.call_args.args[0] == "https://example.com/from-env"


def test_send_discord_message_no_url_returns_false(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    assert send_discord_message("hi") is False


def test_send_discord_message_swallows_request_exception(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    with patch("common.discord.requests.post") as post:
        post.side_effect = requests.exceptions.RequestException("boom")
        assert send_discord_message("hi") is False
