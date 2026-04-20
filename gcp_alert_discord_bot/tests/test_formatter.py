from common.formatter import (
    _fmt_amount,
    _fmt_epoch,
    _truncate,
    format_budget,
    format_monitoring,
    format_pubsub_message,
    format_unknown,
)


class TestFmtAmount:
    def test_none_returns_question_mark(self):
        assert _fmt_amount(None, "JPY") == "?"

    def test_jpy_prefix(self):
        assert _fmt_amount(1000, "JPY") == "¥1,000"

    def test_usd_prefix(self):
        assert _fmt_amount(1000, "USD") == "$1,000"

    def test_integer_float_is_normalized(self):
        assert _fmt_amount(1000.0, "JPY") == "¥1,000"

    def test_non_integer_float_preserved(self):
        assert _fmt_amount(12.5, "USD") == "$12.5"

    def test_unknown_currency_suffixed(self):
        assert _fmt_amount(1234, "EUR") == "1,234 EUR"

    def test_missing_currency(self):
        assert _fmt_amount(100, None) == "100"


class TestFmtEpoch:
    def test_none_returns_empty(self):
        assert _fmt_epoch(None) == ""

    def test_epoch_seconds(self):
        # 2021-01-01T00:00:00Z as epoch
        result = _fmt_epoch(1609459200)
        # Output is local-time formatted, just sanity-check shape
        assert len(result) == len("YYYY-MM-DD HH:MM")
        assert result[4] == "-" and result[7] == "-"

    def test_iso_z_string(self):
        result = _fmt_epoch("2021-01-01T00:00:00Z")
        assert len(result) == len("YYYY-MM-DD HH:MM")

    def test_invalid_string_returns_input(self):
        assert _fmt_epoch("not-a-date") == "not-a-date"


class TestTruncate:
    def test_short_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_long_truncated_with_ellipsis(self):
        result = _truncate("a" * 20, 10)
        assert len(result) == 10
        assert result.endswith("…")

    def test_default_limit(self):
        # default 800
        assert _truncate("x" * 800) == "x" * 800
        result = _truncate("x" * 900)
        assert len(result) == 800


class TestFormatBudget:
    def test_threshold_exceeded_header(self):
        body = {
            "budgetDisplayName": "monthly",
            "alertThresholdExceeded": 0.5,
            "costAmount": 500,
            "budgetAmount": 1000,
            "currencyCode": "JPY",
        }
        out = format_budget(body)
        assert "monthly" in out
        assert "50%" in out
        assert "¥500" in out
        assert "¥1,000" in out

    def test_forecast_threshold(self):
        body = {
            "budgetDisplayName": "monthly",
            "forecastThresholdExceeded": 1.0,
            "costAmount": 800,
            "budgetAmount": 1000,
            "currencyCode": "JPY",
        }
        out = format_budget(body)
        assert "予測" in out
        assert "100%" in out

    def test_without_threshold_plain_header(self):
        body = {"budgetDisplayName": "mybudget"}
        out = format_budget(body)
        assert "通知" in out
        assert "mybudget" in out

    def test_billing_account_from_attrs(self):
        body = {"budgetDisplayName": "b", "costAmount": 1, "budgetAmount": 2}
        out = format_budget(body, {"billingAccountId": "ABC-123"})
        assert "ABC-123" in out

    def test_missing_name_fallback(self):
        out = format_budget({})
        assert "(no name)" in out


class TestFormatMonitoring:
    def test_open_incident(self):
        body = {
            "incident": {
                "state": "OPEN",
                "policy_name": "high-cpu",
                "condition": {"displayName": "CPU > 80%"},
                "resource_display_name": "my-service",
                "summary": "something broke",
                "url": "https://console.cloud.google.com/abc",
                "started_at": 1609459200,
            }
        }
        out = format_monitoring(body)
        assert "🚨" in out
        assert "high-cpu" in out
        assert "CPU > 80%" in out
        assert "my-service" in out
        assert "something broke" in out
        assert "https://console.cloud.google.com/abc" in out

    def test_closed_incident(self):
        body = {
            "incident": {
                "state": "CLOSED",
                "policy_name": "high-cpu",
                "ended_at": 1609459200,
            }
        }
        out = format_monitoring(body)
        assert "✅" in out
        assert "解消" in out
        assert "終了" in out

    def test_unknown_state_defaults_to_bell(self):
        body = {"incident": {"state": "weird", "policy_name": "p"}}
        out = format_monitoring(body)
        assert "🔔" in out

    def test_missing_policy_name(self):
        body = {"incident": {"state": "OPEN"}}
        out = format_monitoring(body)
        assert "(unknown policy)" in out

    def test_summary_truncated(self):
        body = {
            "incident": {
                "state": "OPEN",
                "policy_name": "p",
                "summary": "x" * 2000,
            }
        }
        out = format_monitoring(body)
        # summary is truncated to 800
        assert "…" in out


class TestFormatUnknown:
    def test_wraps_json(self):
        out = format_unknown({"foo": "bar"})
        assert "Unknown" in out
        assert "```json" in out
        assert '"foo": "bar"' in out


class TestFormatPubsubMessage:
    def test_monitoring_dispatch(self):
        body = {"incident": {"state": "OPEN", "policy_name": "p"}}
        assert "Alert" in format_pubsub_message(body, None)

    def test_budget_dispatch_by_display_name(self):
        body = {"budgetDisplayName": "b", "costAmount": 1, "budgetAmount": 2}
        assert "Budget" in format_pubsub_message(body, None)

    def test_budget_dispatch_by_budget_amount(self):
        body = {"budgetAmount": 100, "costAmount": 50}
        assert "Budget" in format_pubsub_message(body, None)

    def test_budget_dispatch_by_attrs(self):
        body = {"costAmount": 50}
        attrs = {"billingAccountId": "X"}
        assert "Budget" in format_pubsub_message(body, attrs)

    def test_unknown_fallback(self):
        assert "Unknown" in format_pubsub_message({"random": "payload"}, {})
