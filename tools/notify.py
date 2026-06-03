#!/usr/bin/env python3
"""Paper-trading P&L digest -> Slack (or stdout).

During the "get more data first" phase the bot places NO real bets. This builds
a concise summary of paper performance and posts it to Slack if SLACK_WEBHOOK_URL
is set, otherwise prints to the terminal. Wire the webhook (env var or
.credentials.local) and the same command starts alerting.

Usage:
    backend/.venv/bin/python3 tools/notify.py
    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \\
        backend/.venv/bin/python3 tools/notify.py
"""
import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _money(x: float) -> str:
    """Conventional signed currency, e.g. -$61.47 / +$9.77."""
    return f"{'-' if x < 0 else '+'}${abs(x):.2f}"


def build_digest(perf: dict, recs: list[dict]) -> str:
    """Build the Slack/terminal digest string from performance + recommendations.

    Pure function (no I/O) so it is deterministic and testable.
    """
    brier = perf.get("overall_brier", 0.0)
    hit = perf.get("hit_rate", 0.0)
    resolved = perf.get("total_resolved", 0)
    sim_pnl = perf.get("simulated_pnl", 0.0)
    real_pnl = perf.get("total_pnl", 0.0)
    active = sum(1 for r in recs if r.get("status") == "active")

    lines = [
        "AugurBot paper update",
        f"Resolved: {resolved} | Brier: {brier:.3f} | Hit: {hit * 100:.0f}%",
        # Note: historical sim_pnl was computed at mid; new resolutions use the
        # executable-ask fix in results.py, so this converges to honest pricing.
        f"Paper P&L (simulated): {_money(sim_pnl)}/contract",
        f"Real P&L to date: {_money(real_pnl)}",
        f"Open (paper) recs: {active} active",
    ]

    bias = perf.get("bias_by_category", {})
    live = [c for c in ("NBA", "NCAA Basketball") if c in bias]
    if live:
        parts = [f"{c} {bias[c].get('weighted_bias', 0.0):+.3f}" for c in live]
        lines.append("Calibration bias: " + ", ".join(parts))

    lines.append("PAPER MODE — no real bets placed. Accumulating data for the "
                 "re-backtest before any live trading.")
    return "\n".join(lines)


def _post_to_slack(webhook: str, text: str) -> None:
    import httpx

    resp = httpx.post(webhook, json={"text": text}, timeout=10.0)
    resp.raise_for_status()


def main() -> None:
    perf = json.loads((DATA_DIR / "performance.json").read_text())
    recs_path = DATA_DIR / "recommendations.json"
    recs = json.loads(recs_path.read_text()) if recs_path.exists() else []
    digest = build_digest(perf, recs)

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if webhook:
        _post_to_slack(webhook, digest)
        print("Posted digest to Slack.")
    else:
        print(digest)
        print("\n(SLACK_WEBHOOK_URL not set — printed to stdout instead of "
              "posting. Set it to enable Slack alerts.)", file=sys.stderr)


if __name__ == "__main__":
    main()
