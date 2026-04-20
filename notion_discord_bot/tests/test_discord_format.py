from common.discord_format import (
    EVENT_ACTION,
    _truncate,
    format_event,
)


class TestTruncate:
    def test_short_unchanged(self):
        assert _truncate("hi", 10) == "hi"

    def test_long_truncated_with_ellipsis(self):
        out = _truncate("x" * 100, 10)
        assert len(out) == 10
        assert out.endswith("…")


class TestFormatEvent:
    def test_basic_page_created_with_url(self):
        enriched = {
            "event": {"type": "page.created"},
            "page_title": "テストページ",
            "page_url": "https://notion.so/p/1",
            "authors": ["Alice"],
        }
        out = format_event(enriched)
        assert "content" in out
        assert "Alice" in out["content"]
        assert "テストページ" in out["content"]
        assert "https://notion.so/p/1" in out["content"]
        assert "を作成" in out["content"]
        assert "embeds" not in out  # no fields

    def test_basic_without_url(self):
        enriched = {
            "event": {"type": "page.deleted"},
            "page_title": "タイトル",
            "authors": ["Bob"],
        }
        out = format_event(enriched)
        assert "Bob" in out["content"]
        # no markdown link when url missing
        assert "](" not in out["content"]
        assert "を削除" in out["content"]

    def test_missing_title_fallback(self):
        enriched = {"event": {"type": "page.created"}}
        out = format_event(enriched)
        assert "(無題)" in out["content"]
        assert "unknown" in out["content"]  # fallback author

    def test_empty_authors_uses_unknown(self):
        enriched = {
            "event": {"type": "page.created"},
            "authors": [None, ""],
            "page_title": "t",
        }
        out = format_event(enriched)
        assert "unknown" in out["content"]

    def test_multiple_authors_joined(self):
        enriched = {
            "event": {"type": "page.created"},
            "authors": ["A", "B"],
            "page_title": "t",
        }
        out = format_event(enriched)
        assert "A, B" in out["content"]

    def test_unknown_event_type_falls_back_to_raw(self):
        enriched = {"event": {"type": "weird.event"}, "page_title": "t"}
        out = format_event(enriched)
        assert "weird.event" in out["content"]

    def test_updated_properties_become_fields(self):
        enriched = {
            "event": {"type": "page.properties_updated"},
            "page_title": "t",
            "updated_properties": [
                {"name": "Status", "value": "Done"},
                {"name": "Tags", "value": "a, b"},
            ],
        }
        out = format_event(enriched)
        assert "embeds" in out
        fields = out["embeds"][0]["fields"]
        assert len(fields) == 2
        assert fields[0]["name"] == "Status"
        assert fields[0]["value"] == "Done"
        assert fields[0]["inline"] is False

    def test_updated_blocks_become_fields(self):
        enriched = {
            "event": {"type": "page.content_updated"},
            "page_title": "t",
            "updated_blocks": [
                {"type": "paragraph", "text": "hello"},
                {"type": "heading_2", "text": ""},  # empty -> "(空)"
            ],
        }
        out = format_event(enriched)
        fields = out["embeds"][0]["fields"]
        assert fields[0]["name"] == "paragraph"
        assert fields[0]["value"] == "hello"
        assert fields[1]["value"] == "(空)"

    def test_long_value_is_truncated(self):
        enriched = {
            "event": {"type": "page.properties_updated"},
            "page_title": "t",
            "updated_properties": [{"name": "p", "value": "x" * 2000}],
        }
        out = format_event(enriched)
        value = out["embeds"][0]["fields"][0]["value"]
        assert len(value) <= 1024
        assert value.endswith("…")

    def test_field_count_capped_at_25(self):
        enriched = {
            "event": {"type": "page.content_updated"},
            "page_title": "t",
            "updated_blocks": [
                {"type": "paragraph", "text": f"b{i}"} for i in range(40)
            ],
        }
        out = format_event(enriched)
        assert len(out["embeds"][0]["fields"]) == 25

    def test_empty_property_value_becomes_placeholder(self):
        enriched = {
            "event": {"type": "page.properties_updated"},
            "page_title": "t",
            "updated_properties": [{"name": "p", "value": ""}],
        }
        out = format_event(enriched)
        assert out["embeds"][0]["fields"][0]["value"] == "(空)"


def test_event_action_covers_expected_types():
    required = {
        "page.created",
        "page.content_updated",
        "page.properties_updated",
        "page.deleted",
        "comment.created",
    }
    assert required.issubset(EVENT_ACTION.keys())
