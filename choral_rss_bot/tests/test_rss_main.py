import time
from datetime import datetime, timedelta
from unittest.mock import patch

from rss.main import format_date, is_within_days, process_entry


def _struct_from_dt(dt: datetime) -> time.struct_time:
    return dt.timetuple()


class TestFormatDate:
    def test_none_returns_current_time_shape(self):
        out = format_date(None)
        # "YYYY/MM/DD HH:MM" shape
        assert len(out) == len("YYYY/MM/DD HH:MM")
        assert out[4] == "/" and out[7] == "/"

    def test_valid_struct_formatted(self):
        dt = datetime(2024, 3, 15, 10, 30)
        out = format_date(_struct_from_dt(dt))
        assert out == "2024/03/15 10:30"

    def test_invalid_struct_falls_back_to_now(self):
        out = format_date("not-a-struct")
        assert len(out) == len("YYYY/MM/DD HH:MM")


class TestIsWithinDays:
    def test_no_date_fields_returns_true(self):
        assert is_within_days({}) is True

    def test_recent_entry_is_within(self):
        recent = datetime.now() - timedelta(days=1)
        entry = {"published_parsed": _struct_from_dt(recent)}
        assert is_within_days(entry, days=30) is True

    def test_old_entry_excluded(self):
        old = datetime.now() - timedelta(days=60)
        entry = {"published_parsed": _struct_from_dt(old)}
        assert is_within_days(entry, days=30) is False

    def test_uses_updated_parsed_fallback(self):
        recent = datetime.now() - timedelta(days=1)
        entry = {"updated_parsed": _struct_from_dt(recent)}
        assert is_within_days(entry, days=30) is True

    def test_custom_threshold(self):
        d = datetime.now() - timedelta(days=5)
        entry = {"published_parsed": _struct_from_dt(d)}
        assert is_within_days(entry, days=3) is False
        assert is_within_days(entry, days=10) is True

    def test_invalid_struct_returns_true(self):
        entry = {"published_parsed": "bogus"}
        assert is_within_days(entry) is True


class TestProcessEntry:
    @patch("rss.main.extract_and_explain_proper_nouns")
    @patch("rss.main.translate_title")
    def test_english_feed_includes_both_titles(self, trans, nouns):
        trans.return_value = "こんにちは世界"
        nouns.return_value = {"explanations": ""}

        dt = datetime(2024, 3, 15, 10, 30)
        entry = {
            "title": "Hello World",
            "link": "https://example.com/a",
            "published_parsed": _struct_from_dt(dt),
        }
        feed = {"name": "Test Feed", "language": "en"}
        result = process_entry(entry, feed, mode="discord")

        assert result["title"] == "Hello World"
        assert result["link"] == "https://example.com/a"
        assert result["display_title"] == "こんにちは世界"
        assert result["source"] == "Test Feed"
        assert "英語タイトル: Hello World" in result["message_text"]
        assert "日本語タイトル: こんにちは世界" in result["message_text"]
        assert "Test Feed" in result["message_text"]
        assert "2024/03/15 10:30" in result["message_text"]

    @patch("rss.main.extract_and_explain_proper_nouns")
    @patch("rss.main.translate_title")
    def test_japanese_feed_shows_single_title(self, trans, nouns):
        trans.return_value = "翻訳後"
        nouns.return_value = {"explanations": ""}

        entry = {"title": "元タイトル", "link": "https://x.jp/1"}
        feed = {"name": "J Feed", "language": "ja"}
        result = process_entry(entry, feed, mode="discord")

        assert "英語タイトル" not in result["message_text"]
        assert "タイトル: 翻訳後" in result["message_text"]

    @patch("rss.main.extract_and_explain_proper_nouns")
    @patch("rss.main.translate_title")
    def test_explanations_appended_when_present(self, trans, nouns):
        trans.return_value = "t"
        nouns.return_value = {"explanations": "用語の解説テキスト"}

        entry = {"title": "x", "link": "https://y/1"}
        feed = {"name": "F", "language": "ja"}
        result = process_entry(entry, feed, mode="discord")
        assert "用語解説" in result["message_text"]
        assert "用語の解説テキスト" in result["message_text"]

    @patch("rss.main.extract_and_explain_proper_nouns")
    @patch("rss.main.translate_title")
    def test_missing_title_and_link_uses_defaults(self, trans, nouns):
        trans.return_value = ""
        nouns.return_value = {"explanations": ""}

        result = process_entry({}, {"name": "F", "language": "ja"}, mode="discord")
        assert result["title"] == "No Title"
        assert result["link"] == ""
