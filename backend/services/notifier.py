"""Notification service — sends alerts after scans find high-EV bets.

Supports two channels:
- Email via Resend API (requires RESEND_API_KEY env var)
- Slack via incoming webhook URL (configured in Settings)
"""

import logging
from datetime import datetime, timezone

import httpx

from config import settings
from models.database import get_config

logger = logging.getLogger(__name__)


async def send_scan_notifications(
    recommendations: list[dict],
    scan_summary: dict,
) -> dict[str, bool]:
    """Send notifications for new recommendations found during a scan.

    Args:
        recommendations: List of dicts with keys: question, direction, edge,
            ev, ai_probability, market_price, kelly_fraction, outcome_label,
            platform_id.
        scan_summary: Dict with keys: markets_found, markets_researched,
            recommendations_created, duration_seconds.

    Returns:
        Dict of {channel: success_bool} for each enabled channel.
    """
    config = get_config()

    if not config.get("notifications_enabled", False):
        return {}

    min_ev = config.get("notification_min_ev", 0.08)
    filtered = [r for r in recommendations if r.get("ev", 0) >= min_ev]

    if not filtered:
        logger.info("Notifier: no recommendations above min EV %.0f%%, skipping", min_ev * 100)
        return {}

    results: dict[str, bool] = {}

    email = config.get("notification_email", "")
    slack_webhook = config.get("notification_slack_webhook", "")

    if email:
        results["email"] = await _send_email(email, filtered, scan_summary)

    if slack_webhook:
        results["slack"] = await _send_slack(slack_webhook, filtered, scan_summary)

    return results


async def send_test_notification() -> dict[str, bool]:
    """Send a test notification to verify configuration."""
    config = get_config()
    test_recs = [
        {
            "question": "Test: Will this notification work?",
            "direction": "yes",
            "edge": 0.12,
            "ev": 0.10,
            "ai_probability": 0.65,
            "market_price": 0.53,
            "kelly_fraction": 0.15,
            "outcome_label": "Yes",
            "platform_id": "TEST-MARKET",
        }
    ]
    test_summary = {
        "markets_found": 25,
        "markets_researched": 10,
        "recommendations_created": 1,
        "duration_seconds": 120,
    }

    results: dict[str, bool] = {}
    email = config.get("notification_email", "")
    slack_webhook = config.get("notification_slack_webhook", "")

    if email:
        results["email"] = await _send_email(email, test_recs, test_summary)
    if slack_webhook:
        results["slack"] = await _send_slack(slack_webhook, test_recs, test_summary)

    if not results:
        logger.warning("Notifier: no channels configured for test")

    return results


def _format_rec_text(rec: dict) -> str:
    """Format a single recommendation for plain text."""
    direction = rec.get("direction", "yes").upper()
    label = rec.get("outcome_label")
    bet_label = f"Bet: {label}" if label else direction
    edge = rec.get("edge", 0) * 100
    ev = rec.get("ev", 0) * 100
    ai_prob = rec.get("ai_probability", 0) * 100
    mkt_price = rec.get("market_price", 0) * 100
    kelly = rec.get("kelly_fraction", 0) * 100
    return (
        f"  {rec.get('question', 'Unknown')}\n"
        f"  {bet_label} | Edge: {edge:.1f}% | EV: {ev:.1f}%\n"
        f"  AI: {ai_prob:.0f}% vs Market: {mkt_price:.0f}% | Kelly: {kelly:.1f}%"
    )


def _format_rec_slack(rec: dict) -> str:
    """Format a single recommendation for Slack markdown."""
    direction = rec.get("direction", "yes").upper()
    label = rec.get("outcome_label")
    bet_label = f"Bet: {label}" if label else direction
    edge = rec.get("edge", 0) * 100
    ev = rec.get("ev", 0) * 100
    ai_prob = rec.get("ai_probability", 0) * 100
    mkt_price = rec.get("market_price", 0) * 100
    kelly = rec.get("kelly_fraction", 0) * 100
    platform_id = rec.get("platform_id", "")
    url = f"https://kalshi.com/markets/{platform_id.lower()}" if platform_id else ""
    question = rec.get("question", "Unknown")
    title = f"<{url}|{question}>" if url else question
    return (
        f"*{title}*\n"
        f"{bet_label} | Edge: {edge:.1f}% | EV: {ev:.1f}%\n"
        f"AI: {ai_prob:.0f}% vs Market: {mkt_price:.0f}% | Kelly: {kelly:.1f}%"
    )


async def _send_email(
    to_email: str,
    recs: list[dict],
    summary: dict,
) -> bool:
    """Send email via Resend API."""
    api_key = getattr(settings, "resend_api_key", "") or ""
    if not api_key:
        logger.warning("Notifier: RESEND_API_KEY not set, skipping email")
        return False

    now = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
    count = len(recs)
    subject = f"AugurBot: {count} high-EV bet{'s' if count != 1 else ''} found ({now})"

    rec_blocks = "\n\n".join(_format_rec_text(r) for r in recs)
    body_text = (
        f"AugurBot scan completed at {now}\n"
        f"Markets found: {summary.get('markets_found', 0)} | "
        f"Researched: {summary.get('markets_researched', 0)} | "
        f"Recommendations: {summary.get('recommendations_created', 0)} | "
        f"Duration: {summary.get('duration_seconds', 0):.0f}s\n\n"
        f"--- High-EV Recommendations ---\n\n"
        f"{rec_blocks}\n\n"
        f"---\nView all: https://augurbot.com"
    )

    # Build simple HTML
    rec_html_items = ""
    for r in recs:
        direction = r.get("direction", "yes").upper()
        label = r.get("outcome_label")
        bet_label = f"Bet: {label}" if label else direction
        edge = r.get("edge", 0) * 100
        ev = r.get("ev", 0) * 100
        ai_prob = r.get("ai_probability", 0) * 100
        mkt_price = r.get("market_price", 0) * 100
        kelly = r.get("kelly_fraction", 0) * 100
        platform_id = r.get("platform_id", "")
        url = f"https://kalshi.com/markets/{platform_id.lower()}" if platform_id else ""
        question = r.get("question", "Unknown")
        title_html = f'<a href="{url}" style="color:#A78BFA">{question}</a>' if url else question
        rec_html_items += (
            f'<div style="margin-bottom:16px;padding:12px;background:#1a1a1e;border-radius:8px">'
            f'<div style="font-weight:600;margin-bottom:4px">{title_html}</div>'
            f'<div style="color:#a1a1aa;font-size:14px">'
            f'{bet_label} &middot; Edge: {edge:.1f}% &middot; EV: {ev:.1f}%<br>'
            f'AI: {ai_prob:.0f}% vs Market: {mkt_price:.0f}% &middot; Kelly: {kelly:.1f}%'
            f'</div></div>'
        )

    body_html = (
        f'<div style="font-family:sans-serif;background:#0a0a0c;color:#fafafa;padding:24px">'
        f'<h2 style="margin-top:0">AugurBot Scan Results</h2>'
        f'<p style="color:#a1a1aa">'
        f'Markets: {summary.get("markets_found", 0)} found, '
        f'{summary.get("markets_researched", 0)} researched, '
        f'{summary.get("recommendations_created", 0)} recommended '
        f'({summary.get("duration_seconds", 0):.0f}s)</p>'
        f'{rec_html_items}'
        f'<p style="margin-top:24px"><a href="https://augurbot.com" style="color:#A78BFA">'
        f'Open AugurBot Dashboard</a></p></div>'
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "from": "AugurBot <notifications@augurbot.com>",
                    "to": [to_email],
                    "subject": subject,
                    "text": body_text,
                    "html": body_html,
                },
            )
        if resp.status_code in (200, 201):
            logger.info("Notifier: email sent to %s", to_email)
            return True
        else:
            logger.error("Notifier: email failed — %d %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Notifier: email send error")
        return False


async def _send_slack(
    webhook_url: str,
    recs: list[dict],
    summary: dict,
) -> bool:
    """Send Slack notification via incoming webhook."""
    now = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
    count = len(recs)

    rec_blocks = "\n\n".join(_format_rec_slack(r) for r in recs)
    text = (
        f":chart_with_upwards_trend: *AugurBot: {count} high-EV bet{'s' if count != 1 else ''} found*\n"
        f"_{now} | {summary.get('markets_found', 0)} markets scanned, "
        f"{summary.get('markets_researched', 0)} researched, "
        f"{summary.get('duration_seconds', 0):.0f}s_\n\n"
        f"{rec_blocks}\n\n"
        f"<https://augurbot.com|Open Dashboard>"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
        if resp.status_code == 200:
            logger.info("Notifier: Slack webhook sent (%d recs)", count)
            return True
        else:
            logger.error("Notifier: Slack failed — %d %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Notifier: Slack send error")
        return False
