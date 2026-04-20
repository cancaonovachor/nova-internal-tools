from pathlib import Path

from common.discord_sender import (
    FileDiscordSender,
    WebhookDiscordSender,
    create_sender,
    render_payload_as_text,
)


class TestRenderPayloadAsText:
    def test_content_only(self):
        assert render_payload_as_text({"content": "hello"}) == "hello"

    def test_embed_with_fields(self):
        payload = {
            "content": "head",
            "embeds": [
                {
                    "title": "T",
                    "description": "D",
                    "fields": [{"name": "n", "value": "v"}],
                }
            ],
        }
        text = render_payload_as_text(payload)
        assert "head" in text
        assert "[embed title] T" in text
        assert "[embed] D" in text
        assert "[embed field] n: v" in text

    def test_empty_payload_returns_json(self):
        text = render_payload_as_text({})
        assert text == "{}"


def test_file_discord_sender_appends(tmp_path: Path):
    out = tmp_path / "sub" / "out.txt"
    sender = FileDiscordSender(out)
    sender.send({"content": "first"})
    sender.send({"content": "second"})
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert "first" in body
    assert "second" in body
    assert body.count("---") == 2  # separator after each send


def test_create_sender_webhook(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    s = create_sender()
    assert isinstance(s, WebhookDiscordSender)


def test_create_sender_file_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("DISCORD_LOG_FILE", str(tmp_path / "d.txt"))
    s = create_sender()
    assert isinstance(s, FileDiscordSender)


def test_create_sender_empty_url_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "   ")
    monkeypatch.setenv("DISCORD_LOG_FILE", str(tmp_path / "d.txt"))
    s = create_sender()
    assert isinstance(s, FileDiscordSender)
