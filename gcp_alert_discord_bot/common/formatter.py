"""GCP Budget / Cloud Monitoring の Pub/Sub ペイロードを Discord message に整形する。

- Budget: Pub/Sub message body そのものが予算通知 JSON
  https://cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications#notification_format
  例: {"budgetDisplayName": "...", "alertThresholdExceeded": 0.5,
       "costAmount": 12.3, "budgetAmount": 20, "currencyCode": "JPY", ...}

- Cloud Monitoring: Pub/Sub message body は alert policy の JSON
  https://cloud.google.com/monitoring/support/notification-options#pubsub
  先頭キーに "incident" を含む。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _fmt_amount(amount: float | int | None, currency: str | None) -> str:
    if amount is None:
        return "?"
    currency = currency or ""
    if isinstance(amount, float) and amount.is_integer():
        amount = int(amount)
    if currency == "JPY":
        return f"¥{amount:,}"
    if currency == "USD":
        return f"${amount:,}"
    return f"{amount:,} {currency}".strip()


def _fmt_epoch(ts: Any) -> str:
    try:
        if ts is None:
            return ""
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def format_budget(body: dict[str, Any], attrs: dict[str, str] | None = None) -> str:
    """Budget notification body → Discord markdown.

    attrs には Pub/Sub message attributes が入る (billingAccountId, schemaVersion など)。
    """
    attrs = attrs or {}
    name = body.get("budgetDisplayName") or "(no name)"
    threshold = body.get("alertThresholdExceeded")
    cost_type = body.get("costIntervalStart")
    currency = body.get("currencyCode")
    cost = body.get("costAmount")
    budget = body.get("budgetAmount")
    forecast = body.get("forecastThresholdExceeded")

    pct = None
    if isinstance(threshold, (int, float)):
        pct = int(threshold * 100)

    if pct is not None:
        header = f"💸 **Budget `{name}` が {pct}% を超過**"
    elif forecast is not None:
        header = f"💸 **Budget `{name}` の予測が {int(forecast * 100)}% を超過**"
    else:
        header = f"💸 **Budget `{name}` 通知**"

    lines = [header]
    lines.append(f"> **現在コスト**: {_fmt_amount(cost, currency)}")
    lines.append(f"> **予算**: {_fmt_amount(budget, currency)}")
    if cost_type:
        lines.append(f"> **期間開始**: {_fmt_epoch(cost_type)}")
    billing_id = attrs.get("billingAccountId")
    if billing_id:
        lines.append(f"> **Billing Account**: `{billing_id}`")
    return "\n".join(lines)


_STATE_EMOJI = {
    "OPEN": "🚨",
    "open": "🚨",
    "CLOSED": "✅",
    "closed": "✅",
}


def format_monitoring(body: dict[str, Any]) -> str:
    """Cloud Monitoring alert body → Discord markdown."""
    incident = body.get("incident") or {}
    state = incident.get("state") or incident.get("status") or "OPEN"
    emoji = _STATE_EMOJI.get(state, "🔔")
    policy = (
        incident.get("policy_name")
        or incident.get("policy_user_labels", {}).get("name")
        or "(unknown policy)"
    )
    condition_name = (incident.get("condition") or {}).get("displayName") or incident.get(
        "condition_name"
    )
    summary = incident.get("summary") or incident.get("documentation", {}).get("content")
    url = incident.get("url")
    resource = incident.get("resource_display_name") or (
        incident.get("resource") or {}
    ).get("type")
    started = incident.get("started_at")
    ended = incident.get("ended_at")

    head_title = f"`{policy}`"
    if state.upper() == "CLOSED":
        header = f"{emoji} **Alert 解消: {head_title}**"
    else:
        header = f"{emoji} **Alert 発生: {head_title}**"
    if url:
        header = f"{header} ([詳細]({url}))"

    lines = [header]
    if condition_name:
        lines.append(f"> **条件**: {condition_name}")
    if resource:
        lines.append(f"> **リソース**: `{resource}`")
    if started:
        lines.append(f"> **開始**: {_fmt_epoch(started)}")
    if ended and state.upper() == "CLOSED":
        lines.append(f"> **終了**: {_fmt_epoch(ended)}")
    if summary:
        lines.append(f"> {_truncate(str(summary), 800)}")
    return "\n".join(lines)


def _truncate(text: str, max_len: int = 800) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_unknown(body: dict[str, Any]) -> str:
    snippet = json.dumps(body, ensure_ascii=False)[:1500]
    return f"❓ **Unknown GCP alert**\n```json\n{snippet}\n```"


def format_pubsub_message(body: dict[str, Any], attrs: dict[str, str] | None) -> str:
    """ペイロードから種別を判定して整形済み Discord markdown を返す。"""
    attrs = attrs or {}
    if "incident" in body:
        return format_monitoring(body)
    if "budgetDisplayName" in body or "budgetAmount" in body:
        return format_budget(body, attrs)
    # attributes から判別 (予算通知は billingAccountId 属性が付く)
    if attrs.get("billingAccountId") or attrs.get("schemaVersion"):
        return format_budget(body, attrs)
    logger.warning("unknown payload shape: keys=%s attrs=%s", list(body.keys()), attrs)
    return format_unknown(body)
