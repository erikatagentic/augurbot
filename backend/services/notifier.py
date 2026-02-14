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


async def send_daily_digest() -> dict[str, bool]:
    """Send a daily digest summarizing the day's activity.

    Covers: recommendations created, trades placed, markets resolved, cost.
    Skips sending if there was no activity today.
    """
    config = get_config()
    if not config.get("notifications_enabled", False):
        return {}
    if not config.get("daily_digest_enabled", True):
        return {}

    from models.database import get_supabase

    db = get_supabase()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Count today's recommendations
    recs_result = (
        db.table("recommendations")
        .select("id", count="exact")
        .gte("created_at", f"{today}T00:00:00Z")
        .execute()
    )
    recs_today = recs_result.count or 0

    # Count today's trades
    trades_result = (
        db.table("trades")
        .select("id", count="exact")
        .gte("created_at", f"{today}T00:00:00Z")
        .execute()
    )
    trades_today = trades_result.count or 0

    # Count today's resolutions
    perf_result = (
        db.table("performance_log")
        .select("id, pnl", count="exact")
        .gte("resolved_at", f"{today}T00:00:00Z")
        .execute()
    )
    resolved_today = perf_result.count or 0
    today_pnl = sum(row.get("pnl", 0) or 0 for row in (perf_result.data or []))

    # Today's API cost
    cost_result = (
        db.table("cost_log")
        .select("estimated_cost")
        .gte("created_at", f"{today}T00:00:00Z")
        .execute()
    )
    today_cost = sum(row.get("estimated_cost", 0) for row in (cost_result.data or []))

    # Skip if no activity
    if recs_today == 0 and trades_today == 0 and resolved_today == 0:
        logger.info("Daily digest: no activity today, skipping")
        return {}

    now_str = datetime.now(timezone.utc).strftime("%b %d, %Y")
    results: dict[str, bool] = {}

    email = config.get("notification_email", "")
    slack_webhook = config.get("notification_slack_webhook", "")

    if email:
        results["email"] = await _send_daily_digest_email(
            email, now_str, recs_today, trades_today, resolved_today, today_pnl, today_cost,
        )
    if slack_webhook:
        results["slack"] = await _send_daily_digest_slack(
            slack_webhook, now_str, recs_today, trades_today, resolved_today, today_pnl, today_cost,
        )

    return results


async def _send_daily_digest_email(
    to_email: str,
    date_str: str,
    recs: int,
    trades: int,
    resolved: int,
    pnl: float,
    cost: float,
) -> bool:
    """Send daily digest email via Resend."""
    api_key = getattr(settings, "resend_api_key", "") or ""
    if not api_key:
        return False

    subject = f"AugurBot Daily Digest — {date_str}"
    pnl_sign = "+" if pnl >= 0 else ""
    body_text = (
        f"AugurBot Daily Digest for {date_str}\n\n"
        f"Recommendations: {recs}\n"
        f"Trades placed: {trades}\n"
        f"Markets resolved: {resolved}\n"
        f"P&L today: {pnl_sign}${pnl:.2f}\n"
        f"API cost: ${cost:.2f}\n\n"
        f"View details: https://augurbot.com"
    )
    pnl_color = "#34D399" if pnl >= 0 else "#F87171"
    body_html = (
        f'<div style="font-family:sans-serif;background:#0a0a0c;color:#fafafa;padding:24px">'
        f'<h2 style="margin-top:0">Daily Digest — {date_str}</h2>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:16px 0">'
        f'<div style="background:#1a1a1e;border-radius:8px;padding:12px">'
        f'<div style="color:#a1a1aa;font-size:12px">Recommendations</div>'
        f'<div style="font-size:24px;font-weight:600">{recs}</div></div>'
        f'<div style="background:#1a1a1e;border-radius:8px;padding:12px">'
        f'<div style="color:#a1a1aa;font-size:12px">Trades Placed</div>'
        f'<div style="font-size:24px;font-weight:600">{trades}</div></div>'
        f'<div style="background:#1a1a1e;border-radius:8px;padding:12px">'
        f'<div style="color:#a1a1aa;font-size:12px">Resolved</div>'
        f'<div style="font-size:24px;font-weight:600">{resolved}</div></div>'
        f'<div style="background:#1a1a1e;border-radius:8px;padding:12px">'
        f'<div style="color:#a1a1aa;font-size:12px">P&L Today</div>'
        f'<div style="font-size:24px;font-weight:600;color:{pnl_color}">'
        f'{pnl_sign}${pnl:.2f}</div></div>'
        f'</div>'
        f'<p style="color:#a1a1aa;font-size:14px">API cost today: ${cost:.2f}</p>'
        f'<p style="margin-top:24px"><a href="https://augurbot.com" style="color:#A78BFA">'
        f'Open Dashboard</a></p></div>'
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
            logger.info("Daily digest email sent to %s", to_email)
            return True
        else:
            logger.error("Daily digest email failed: %d %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Daily digest email error")
        return False


async def _send_daily_digest_slack(
    webhook_url: str,
    date_str: str,
    recs: int,
    trades: int,
    resolved: int,
    pnl: float,
    cost: float,
) -> bool:
    """Send daily digest to Slack."""
    pnl_sign = "+" if pnl >= 0 else ""
    text = (
        f":newspaper: *AugurBot Daily Digest — {date_str}*\n\n"
        f"Recommendations: *{recs}*\n"
        f"Trades placed: *{trades}*\n"
        f"Markets resolved: *{resolved}*\n"
        f"P&L today: *{pnl_sign}${pnl:.2f}*\n"
        f"API cost: ${cost:.2f}\n\n"
        f"<https://augurbot.com|Open Dashboard>"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
        if resp.status_code == 200:
            logger.info("Daily digest Slack sent")
            return True
        else:
            logger.error("Daily digest Slack failed: %d %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Daily digest Slack error")
        return False


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
    lines = [
        f"  {rec.get('question', 'Unknown')}",
        f"  {bet_label} | Edge: {edge:.1f}% | EV: {ev:.1f}%",
        f"  AI: {ai_prob:.0f}% vs Market: {mkt_price:.0f}% | Kelly: {kelly:.1f}%",
    ]
    trade = rec.get("auto_trade")
    if trade:
        lines.append(
            f"  >> AUTO-TRADED: {trade['contracts']} contracts at {trade['price_cents']}c (${trade['amount']:.2f})"
        )
    return "\n".join(lines)


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
    lines = [
        f"*{title}*",
        f"{bet_label} | Edge: {edge:.1f}% | EV: {ev:.1f}%",
        f"AI: {ai_prob:.0f}% vs Market: {mkt_price:.0f}% | Kelly: {kelly:.1f}%",
    ]
    trade = rec.get("auto_trade")
    if trade:
        lines.append(
            f":white_check_mark: *Auto-traded: {trade['contracts']} contracts at {trade['price_cents']}c (${trade['amount']:.2f})*"
        )
    return "\n".join(lines)


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
        trade = r.get("auto_trade")
        trade_html = ""
        if trade:
            trade_html = (
                f'<div style="margin-top:6px;padding:6px 8px;background:#166534;border-radius:4px;'
                f'color:#4ade80;font-size:13px;font-weight:600">'
                f'Auto-traded: {trade["contracts"]} contracts at {trade["price_cents"]}c '
                f'(${trade["amount"]:.2f})</div>'
            )
        rec_html_items += (
            f'<div style="margin-bottom:16px;padding:12px;background:#1a1a1e;border-radius:8px">'
            f'<div style="font-weight:600;margin-bottom:4px">{title_html}</div>'
            f'<div style="color:#a1a1aa;font-size:14px">'
            f'{bet_label} &middot; Edge: {edge:.1f}% &middot; EV: {ev:.1f}%<br>'
            f'AI: {ai_prob:.0f}% vs Market: {mkt_price:.0f}% &middot; Kelly: {kelly:.1f}%'
            f'</div>{trade_html}</div>'
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


# ── Sweep trade notifications ──


async def send_sweep_notifications(
    sweep_trades: list[dict],
) -> dict[str, bool]:
    """Send notifications for trades placed during the auto-trade sweep.

    These are trades placed on existing active recommendations that had
    no prior trade.  Uses the same rec dict format as scan notifications
    (each item includes an ``auto_trade`` sub-dict).
    """
    config = get_config()

    if not config.get("notifications_enabled", False):
        return {}

    if not sweep_trades:
        return {}

    results: dict[str, bool] = {}

    email = config.get("notification_email", "")
    slack_webhook = config.get("notification_slack_webhook", "")

    if email:
        results["email"] = await _send_sweep_email(email, sweep_trades)

    if slack_webhook:
        results["slack"] = await _send_sweep_slack(slack_webhook, sweep_trades)

    return results


async def _send_sweep_email(
    to_email: str,
    trades: list[dict],
) -> bool:
    """Send sweep trade notification via Resend."""
    api_key = getattr(settings, "resend_api_key", "") or ""
    if not api_key:
        return False

    now = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
    count = len(trades)
    subject = f"AugurBot: {count} sweep trade{'s' if count != 1 else ''} placed ({now})"

    rec_blocks = "\n\n".join(_format_rec_text(t) for t in trades)
    body_text = (
        f"AugurBot auto-trade sweep at {now}\n"
        f"Placed {count} trade{'s' if count != 1 else ''} on existing recommendations.\n\n"
        f"--- Sweep Trades ---\n\n"
        f"{rec_blocks}\n\n"
        f"---\nView trades: https://augurbot.com/trades"
    )

    # Build HTML (reuse same card style as scan notifications)
    rec_html_items = ""
    for r in trades:
        direction = r.get("direction", "yes").upper()
        label = r.get("outcome_label")
        bet_label = f"Bet: {label}" if label else direction
        edge = r.get("edge", 0) * 100
        ev = r.get("ev", 0) * 100
        ai_prob = r.get("ai_probability", 0) * 100
        mkt_price = r.get("market_price", 0) * 100
        platform_id = r.get("platform_id", "")
        url = f"https://kalshi.com/markets/{platform_id.lower()}" if platform_id else ""
        question = r.get("question", "Unknown")
        title_html = f'<a href="{url}" style="color:#A78BFA">{question}</a>' if url else question
        trade = r.get("auto_trade")
        trade_html = ""
        if trade:
            trade_html = (
                f'<div style="margin-top:6px;padding:6px 8px;background:#166534;border-radius:4px;'
                f'color:#4ade80;font-size:13px;font-weight:600">'
                f'Placed: {trade["contracts"]} contracts at {trade["price_cents"]}c '
                f'(${trade["amount"]:.2f})</div>'
            )
        rec_html_items += (
            f'<div style="margin-bottom:16px;padding:12px;background:#1a1a1e;border-radius:8px">'
            f'<div style="font-weight:600;margin-bottom:4px">{title_html}</div>'
            f'<div style="color:#a1a1aa;font-size:14px">'
            f'{bet_label} &middot; Edge: {edge:.1f}% &middot; EV: {ev:.1f}%<br>'
            f'AI: {ai_prob:.0f}% vs Market: {mkt_price:.0f}%'
            f'</div>{trade_html}</div>'
        )

    body_html = (
        f'<div style="font-family:sans-serif;background:#0a0a0c;color:#fafafa;padding:24px">'
        f'<h2 style="margin-top:0">Auto-Trade Sweep</h2>'
        f'<p style="color:#a1a1aa">Placed {count} trade{"s" if count != 1 else ""} '
        f'on existing recommendations at {now}</p>'
        f'{rec_html_items}'
        f'<p style="margin-top:24px"><a href="https://augurbot.com/trades" style="color:#A78BFA">'
        f'View Trades</a></p></div>'
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
            logger.info("Notifier: sweep email sent to %s (%d trades)", to_email, count)
            return True
        else:
            logger.error("Notifier: sweep email failed — %d %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Notifier: sweep email error")
        return False


async def _send_sweep_slack(
    webhook_url: str,
    trades: list[dict],
) -> bool:
    """Send sweep trade notification to Slack."""
    now = datetime.now(timezone.utc).strftime("%b %d, %H:%M UTC")
    count = len(trades)

    rec_blocks = "\n\n".join(_format_rec_slack(t) for t in trades)
    text = (
        f":arrows_counterclockwise: *AugurBot: {count} sweep trade{'s' if count != 1 else ''} placed*\n"
        f"_{now} | Trades placed on existing recommendations_\n\n"
        f"{rec_blocks}\n\n"
        f"<https://augurbot.com/trades|View Trades>"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
        if resp.status_code == 200:
            logger.info("Notifier: sweep Slack sent (%d trades)", count)
            return True
        else:
            logger.error("Notifier: sweep Slack failed — %d %s", resp.status_code, resp.text[:200])
            return False
    except Exception:
        logger.exception("Notifier: sweep Slack error")
        return False
