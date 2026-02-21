#!/usr/bin/env python3
"""Check market resolutions, update performance tracking, generate calibration feedback.

Usage:
    python3 tools/results.py              # Check all open bets/recommendations
    python3 tools/results.py --stats      # Show stats only (no API calls)
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend/ to import path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import httpx  # noqa: E402
from services.kalshi import KalshiClient  # noqa: E402
from services.http_utils import request_with_retry  # noqa: E402

RECS_FILE = DATA_DIR / "recommendations.json"
BETS_FILE = DATA_DIR / "bets.json"
PERF_FILE = DATA_DIR / "performance.json"
FEEDBACK_FILE = DATA_DIR / "calibration_feedback.txt"
BANKROLL_FILE = DATA_DIR / "bankroll_history.json"


# ── Normalization helpers ──

SPORT_TYPE_CANONICAL = {
    "NCAAB": "NCAA Basketball",
    "ncaab": "NCAA Basketball",
    "College Basketball": "NCAA Basketball",
}


def normalize_sport_type(sport_type: str | None) -> str | None:
    if not sport_type:
        return sport_type
    return SPORT_TYPE_CANONICAL.get(sport_type, sport_type)


def normalize_confidence(conf: str | None) -> str:
    if not conf:
        return "medium"
    conf = conf.lower().strip()
    if conf in ("high",):
        return "high"
    elif conf in ("low", "low-medium"):
        return "low"
    return "medium"  # medium, medium-high, etc.


# ── Date parsing ──

_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_TICKER_DATE_RE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")


def _parse_ticker_date(ticker: str) -> datetime | None:
    """Extract the market date from a Kalshi ticker, return as UTC datetime."""
    m = _TICKER_DATE_RE.search(ticker)
    if not m:
        return None
    yy, mon, dd = m.group(1), m.group(2), m.group(3)
    month = _MONTH_MAP.get(mon)
    if not month:
        return None
    return datetime(2000 + int(yy), month, int(dd), 23, 59, 59, tzinfo=timezone.utc)


# ── JSON helpers ──

def load_json(path: Path) -> list | dict:
    if not path.exists():
        return [] if path.name != "performance.json" else {
            "last_updated": None,
            "total_estimates": 0,
            "total_recommended": 0,
            "total_resolved": 0,
            "overall_brier": 0.0,
            "hit_rate": 0.0,
            "total_pnl": 0.0,
            "simulated_pnl": 0.0,
            "bias_by_category": {},
            "resolved_markets": [],
        }
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: list | dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


# ── Dedup helpers ──

def _dedup_resolved(resolved: list[dict]) -> list[dict]:
    """Keep only the first resolved entry per ticker."""
    seen: set[str] = set()
    deduped: list[dict] = []
    removed = 0
    for entry in resolved:
        ticker = entry.get("ticker", "")
        if ticker in seen:
            removed += 1
            continue
        seen.add(ticker)
        deduped.append(entry)
    if removed:
        print(f"  Deduped {removed} duplicate resolved entries.")
    return deduped


def _backfill_from_recs(resolved: list[dict], recs: list[dict]) -> None:
    """Fill missing confidence/scan_time in resolved entries from recommendations."""
    rec_by_ticker: dict[str, dict] = {}
    for rec in recs:
        ticker = rec.get("ticker", "")
        if ticker and ticker not in rec_by_ticker:
            rec_by_ticker[ticker] = rec

    for entry in resolved:
        if entry.get("confidence") and entry.get("scan_time"):
            continue
        rec = rec_by_ticker.get(entry.get("ticker", ""))
        if rec:
            if not entry.get("confidence"):
                entry["confidence"] = rec.get("confidence", "medium")
            if not entry.get("scan_time"):
                entry["scan_time"] = rec.get("scan_time")
        # Normalize sport_type while we're here
        entry["sport_type"] = normalize_sport_type(entry.get("sport_type"))


# ── Core logic ──

async def check_resolutions() -> None:
    """Check Kalshi for resolved markets, update local tracking."""
    recs = load_json(RECS_FILE)
    bets = load_json(BETS_FILE)
    perf = load_json(PERF_FILE)

    if not isinstance(recs, list):
        recs = []
    if not isinstance(bets, list):
        bets = []

    # Dedup existing resolved markets
    perf["resolved_markets"] = _dedup_resolved(perf.get("resolved_markets", []))

    # Backfill confidence/scan_time from recs
    _backfill_from_recs(perf["resolved_markets"], recs)

    # Find active/open items that need checking
    active_tickers = set()
    for rec in recs:
        if rec.get("status") == "active":
            active_tickers.add(rec["ticker"])
    for bet in bets:
        if bet.get("status") == "open":
            active_tickers.add(bet["ticker"])

    if not active_tickers:
        print("\nNo active recommendations or open bets to check.")
        _recalculate_and_save(perf, recs, bets)
        return

    print(f"\nChecking {len(active_tickers)} markets for resolutions...")

    client = KalshiClient()
    results = await client.check_resolutions_batch(list(active_tickers))

    new_resolutions = 0
    now = datetime.now(timezone.utc).isoformat()

    for ticker, result in results.items():
        if not result.get("resolved"):
            continue

        new_resolutions += 1
        outcome = result.get("outcome")  # True=YES, False=NO

        # Update recommendations
        for rec in recs:
            if rec["ticker"] == ticker and rec.get("status") == "active":
                rec["status"] = "resolved"
                rec["outcome"] = outcome
                rec["resolved_at"] = now

                # Normalize sport_type
                rec["sport_type"] = normalize_sport_type(rec.get("sport_type"))

                # Calculate Brier score
                actual = 1.0 if outcome else 0.0
                brier = (rec["ai_estimate"] - actual) ** 2
                rec["brier_score"] = round(brier, 4)

                # Determine if our bet direction was correct
                if rec["direction"] == "yes":
                    rec["correct"] = outcome is True
                else:
                    rec["correct"] = outcome is False

                # Add to performance resolved list
                perf_entry = {
                    "ticker": ticker,
                    "question": rec.get("question", ""),
                    "category": rec.get("category", ""),
                    "sport_type": rec.get("sport_type", ""),
                    "ai_estimate": rec["ai_estimate"],
                    "market_price": rec["market_price"],
                    "direction": rec["direction"],
                    "outcome": outcome,
                    "brier_score": round(brier, 4),
                    "correct": rec["correct"],
                    "resolved_at": now,
                    "confidence": rec.get("confidence", "medium"),
                    "scan_time": rec.get("scan_time"),
                    "simulated_pnl_per_contract": 0.0,
                }

                # Calculate simulated P&L
                if rec["correct"]:
                    if rec["direction"] == "yes":
                        sim_profit = (1 - rec["market_price"])
                    else:
                        sim_profit = rec["market_price"]
                else:
                    if rec["direction"] == "yes":
                        sim_profit = -rec["market_price"]
                    else:
                        sim_profit = -(1 - rec["market_price"])
                perf_entry["simulated_pnl_per_contract"] = round(sim_profit, 4)

                perf["resolved_markets"].append(perf_entry)

                status_icon = "W" if rec["correct"] else "L"
                print(f"  [{status_icon}] {rec.get('question', ticker)}")
                print(f"      AI: {rec['ai_estimate']:.0%} | Market: {rec['market_price']:.0%} | "
                      f"Bet: {rec['direction'].upper()} | Outcome: {'YES' if outcome else 'NO'} | "
                      f"Brier: {brier:.3f}")

        # Update bets
        for bet in bets:
            if bet["ticker"] == ticker and bet.get("status") == "open":
                bet["status"] = "closed"
                bet["closed_at"] = now

                # Capture closing price for CLV tracking
                # last_price is saved by positions.py each time it runs
                closing = bet.get("last_price", bet["yes_price"])
                bet["closing_price"] = closing
                entry = bet["yes_price"]
                if bet["direction"] == "yes":
                    bet["clv"] = round((closing - entry) / 100, 4)  # positive = line moved in our favor
                else:
                    bet["clv"] = round((entry - closing) / 100, 4)

                # Calculate actual P&L
                yes_price_dec = bet["yes_price"] / 100
                contracts = bet["contracts"]
                if bet["direction"] == "yes":
                    if outcome:
                        bet["pnl"] = round(contracts * (1 - yes_price_dec), 2)
                    else:
                        bet["pnl"] = round(-contracts * yes_price_dec, 2)
                else:  # NO bet
                    if not outcome:
                        bet["pnl"] = round(contracts * yes_price_dec, 2)
                    else:
                        bet["pnl"] = round(-contracts * (1 - yes_price_dec), 2)

                clv_str = f" | CLV: {bet['clv']:+.1%}" if bet.get("clv") else ""
                print(f"      Bet P&L: ${bet['pnl']:+.2f} ({contracts} contracts){clv_str}")

    if new_resolutions == 0:
        print("  No new resolutions found.")
    else:
        print(f"\n  {new_resolutions} market(s) resolved.")

    # Expire stale active recs that returned 404 and whose market date has passed
    expired_count = 0
    for rec in recs:
        if rec.get("status") != "active":
            continue
        ticker = rec["ticker"]
        if ticker in results:
            continue
        market_date = _parse_ticker_date(ticker)
        if market_date and market_date < datetime.now(timezone.utc):
            rec["status"] = "expired"
            rec["expired_reason"] = "api_404_past_date"
            expired_count += 1
    if expired_count:
        print(f"  {expired_count} stale rec(s) expired (404 + past date).")

    # Dedup again after new entries added
    perf["resolved_markets"] = _dedup_resolved(perf.get("resolved_markets", []))

    _recalculate_and_save(perf, recs, bets, now)

    # Save bankroll snapshot
    await _save_bankroll_snapshot(perf, recs, bets)


def _recalculate_and_save(perf: dict, recs: list, bets: list, now: str | None = None) -> None:
    """Recalculate aggregate stats, save files, generate feedback, print stats."""
    if now is None:
        now = datetime.now(timezone.utc).isoformat()

    resolved = perf.get("resolved_markets", [])
    if resolved:
        perf["total_resolved"] = len(resolved)
        perf["overall_brier"] = round(
            sum(r["brier_score"] for r in resolved) / len(resolved), 4
        )
        correct_count = sum(1 for r in resolved if r.get("correct"))
        perf["hit_rate"] = round(correct_count / len(resolved), 4)

        # Actual P&L from bets
        closed_bets = [b for b in bets if b.get("status") == "closed" and b.get("pnl") is not None]
        perf["total_pnl"] = round(sum(b["pnl"] for b in closed_bets), 2)

        # Simulated P&L
        perf["simulated_pnl"] = round(
            sum(r.get("simulated_pnl_per_contract", 0) for r in resolved), 4
        )

        # Bias by category (normalized)
        categories: dict[str, list[float]] = {}
        for r in resolved:
            cat = normalize_sport_type(r.get("sport_type")) or r.get("category", "Other")
            actual = 1.0 if r["outcome"] else 0.0
            bias = r["ai_estimate"] - actual
            categories.setdefault(cat, []).append(bias)

        perf["bias_by_category"] = {
            cat: round(sum(biases) / len(biases), 4)
            for cat, biases in categories.items()
        }

        # Stats by confidence level
        conf_groups: dict[str, list[dict]] = {}
        for r in resolved:
            conf = normalize_confidence(r.get("confidence"))
            conf_groups.setdefault(conf, []).append(r)

        perf["stats_by_confidence"] = {}
        for conf, entries in conf_groups.items():
            n = len(entries)
            brier = sum(e["brier_score"] for e in entries) / n
            correct = sum(1 for e in entries if e.get("correct"))
            sim_pnl = sum(e.get("simulated_pnl_per_contract", 0) for e in entries)
            perf["stats_by_confidence"][conf] = {
                "count": n,
                "brier": round(brier, 4),
                "hit_rate": round(correct / n, 4),
                "simulated_pnl": round(sim_pnl, 4),
            }

        # Stats by direction
        dir_groups: dict[str, list[dict]] = {}
        for r in resolved:
            d = r.get("direction", "unknown")
            dir_groups.setdefault(d, []).append(r)

        perf["stats_by_direction"] = {}
        for d, entries in dir_groups.items():
            n = len(entries)
            brier = sum(e["brier_score"] for e in entries) / n
            correct = sum(1 for e in entries if e.get("correct"))
            perf["stats_by_direction"][d] = {
                "count": n,
                "brier": round(brier, 4),
                "hit_rate": round(correct / n, 4),
            }

        # CLV stats from closed bets
        clv_bets = [b for b in bets if b.get("status") == "closed" and b.get("clv") is not None]
        if clv_bets:
            avg_clv = sum(b["clv"] for b in clv_bets) / len(clv_bets)
            positive_clv = sum(1 for b in clv_bets if b["clv"] > 0)
            perf["clv_stats"] = {
                "count": len(clv_bets),
                "avg_clv": round(avg_clv, 4),
                "positive_clv_pct": round(positive_clv / len(clv_bets), 4),
            }
            # CLV by category
            clv_by_cat: dict[str, list[float]] = {}
            bet_ticker_map = {b["ticker"]: b for b in clv_bets}
            for rec in recs:
                if rec["ticker"] in bet_ticker_map:
                    cat = normalize_sport_type(rec.get("sport_type")) or rec.get("category", "Other")
                    clv_by_cat.setdefault(cat, []).append(bet_ticker_map[rec["ticker"]]["clv"])
            if clv_by_cat:
                perf["clv_by_category"] = {
                    cat: round(sum(vals) / len(vals), 4)
                    for cat, vals in clv_by_cat.items()
                }

        # Stats by scan batch
        scan_groups: dict[str, list[dict]] = {}
        for r in resolved:
            st = r.get("scan_time", "unknown")
            scan_groups.setdefault(st, []).append(r)

        perf["stats_by_scan"] = {}
        for st, entries in sorted(scan_groups.items()):
            n = len(entries)
            brier = sum(e["brier_score"] for e in entries) / n
            correct = sum(1 for e in entries if e.get("correct"))
            perf["stats_by_scan"][st] = {
                "count": n,
                "brier": round(brier, 4),
                "hit_rate": round(correct / n, 4),
            }

    perf["total_estimates"] = len(recs)
    perf["total_recommended"] = sum(1 for r in recs if r.get("ev", 0) >= 0.03)
    perf["last_updated"] = now

    # Save updated files
    save_json(RECS_FILE, recs)
    save_json(BETS_FILE, bets)
    save_json(PERF_FILE, perf)

    # Generate calibration feedback
    generate_feedback(perf)

    # Print stats
    print_stats(perf, recs, bets)


async def _save_bankroll_snapshot(perf: dict, recs: list, bets: list) -> None:
    """Append a bankroll snapshot to bankroll_history.json."""
    try:
        client = KalshiClient()
        await client._ensure_auth()
        path = "/trade-api/v2/portfolio/balance"
        headers = client._auth_headers("GET", path)
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await request_with_retry(
                http, "GET",
                f"{client.base_url}/portfolio/balance",
                headers=headers,
            )
        bal = resp.json()
        cash = bal.get("balance", 0) / 100
        portfolio = bal.get("portfolio_value", 0) / 100
    except Exception:
        cash = 0.0
        portfolio = 0.0

    open_bets_list = [b for b in bets if b.get("status") == "open"]

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kalshi_cash": round(cash, 2),
        "kalshi_portfolio": round(portfolio, 2),
        "kalshi_total": round(cash + portfolio, 2),
        "open_bets_count": len(open_bets_list),
        "resolved_count": perf.get("total_resolved", 0),
        "brier": perf.get("overall_brier", 0),
        "hit_rate": perf.get("hit_rate", 0),
        "actual_pnl": perf.get("total_pnl", 0),
    }

    history: list[dict] = []
    if BANKROLL_FILE.exists():
        with open(BANKROLL_FILE) as f:
            history = json.load(f)
    history.append(snapshot)
    save_json(BANKROLL_FILE, history)
    print(f"\n  Bankroll snapshot saved to {BANKROLL_FILE.relative_to(PROJECT_DIR)}")


# ── Feedback generation ──

def generate_feedback(perf: dict) -> None:
    """Write calibration_feedback.txt for use in future scans."""
    resolved = perf.get("resolved_markets", [])
    if not resolved:
        return

    lines = [
        f"CALIBRATION FEEDBACK (updated {perf.get('last_updated', 'unknown')}):",
        f"- Overall Brier: {perf.get('overall_brier', 0):.3f} (N={len(resolved)} markets). Target: <0.18",
        f"- Hit rate: {perf.get('hit_rate', 0):.0%} on {perf.get('total_recommended', 0)} recommended bets",
        f"- Total P&L: ${perf.get('total_pnl', 0):+.2f} (actual bets placed)",
    ]

    # Bias by category
    bias = perf.get("bias_by_category", {})
    for cat, avg_bias in sorted(bias.items()):
        if abs(avg_bias) < 0.03:
            lines.append(f"- {cat}: Well-calibrated ({avg_bias:+.0%} bias)")
        elif avg_bias > 0:
            lines.append(f"- {cat}: You OVERESTIMATE by ~{abs(avg_bias):.0%}. Lower your estimates.")
        else:
            lines.append(f"- {cat}: You UNDERESTIMATE by ~{abs(avg_bias):.0%}. Raise your estimates.")

    # Confidence-level feedback
    conf_stats = perf.get("stats_by_confidence", {})
    if conf_stats:
        lines.append("")
        lines.append("CONFIDENCE CALIBRATION:")
        for conf in ["high", "medium", "low"]:
            if conf not in conf_stats:
                continue
            s = conf_stats[conf]
            n = s.get("count", 0)
            if n < 5:
                lines.append(f"- {conf.upper()}: {n} bets (too few to evaluate)")
            elif s["brier"] < 0.15:
                lines.append(f"- {conf.upper()}: Well-calibrated (Brier {s['brier']:.3f}, "
                             f"hit {s['hit_rate']:.0%}, N={n}). Keep using this level.")
            elif s["hit_rate"] < 0.40:
                lines.append(f"- {conf.upper()}: OVERCONFIDENT. Brier {s['brier']:.3f}, "
                             f"hit only {s['hit_rate']:.0%} (N={n}). Tighten criteria.")
            else:
                lines.append(f"- {conf.upper()}: Brier {s['brier']:.3f}, hit {s['hit_rate']:.0%} (N={n})")

    # Trend feedback
    scan_stats = perf.get("stats_by_scan", {})
    if len(scan_stats) >= 3:
        briers = [s["brier"] for _, s in sorted(scan_stats.items())]
        recent_3 = briers[-3:]
        trend = " -> ".join(f"{b:.3f}" for b in recent_3)
        if recent_3[-1] < recent_3[0]:
            lines.append(f"\nTREND: Last 3 scans Brier: {trend} (improving)")
        else:
            lines.append(f"\nTREND: Last 3 scans Brier: {trend} (deteriorating)")

    # CLV note (supplementary, not primary)
    clv_stats = perf.get("clv_stats")
    if clv_stats and clv_stats.get("count", 0) >= 5:
        avg_clv = clv_stats["avg_clv"]
        pos_pct = clv_stats["positive_clv_pct"]
        lines.append(f"\nCLV (supplementary): Avg {avg_clv:+.1%}, {pos_pct:.0%} of bets beat the closing line.")
        if avg_clv > 0.02:
            lines.append("Positive CLV suggests we're identifying edge before the market corrects. Good sign.")
        elif avg_clv < -0.02:
            lines.append("Negative CLV suggests the market moves against us. Consider scanning earlier.")

    lines.append("\nAdjust your estimates accordingly in future research.")

    with open(FEEDBACK_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n  Calibration feedback saved to {FEEDBACK_FILE.relative_to(PROJECT_DIR)}")


# ── Display ──

def print_stats(perf: dict, recs: list, bets: list) -> None:
    """Print summary statistics."""
    resolved = perf.get("resolved_markets", [])
    active_recs = [r for r in recs if r.get("status") == "active"]
    open_bets = [b for b in bets if b.get("status") == "open"]
    closed_bets = [b for b in bets if b.get("status") == "closed"]

    print(f"\n{'='*60}")
    print(f"  PERFORMANCE SUMMARY")
    print(f"{'='*60}")
    print(f"  Total estimates:      {perf.get('total_estimates', 0)}")
    print(f"  Total recommended:    {perf.get('total_recommended', 0)}")
    print(f"  Resolved:             {len(resolved)}")
    print(f"  Active recs:          {len(active_recs)}")
    print(f"  Open bets:            {len(open_bets)}")
    print(f"  Closed bets:          {len(closed_bets)}")

    if resolved:
        print(f"\n  Overall Brier:        {perf.get('overall_brier', 0):.3f}")
        print(f"  Hit rate:             {perf.get('hit_rate', 0):.0%}")
        print(f"  Actual P&L:           ${perf.get('total_pnl', 0):+.2f}")
        print(f"  Simulated P&L:        ${perf.get('simulated_pnl', 0):+.4f} (per contract)")

        # Bias by category
        bias = perf.get("bias_by_category", {})
        if bias:
            print(f"\n  BIAS BY CATEGORY:")
            for cat, avg in sorted(bias.items()):
                direction = "over" if avg > 0 else "under"
                print(f"    {cat:<20} {avg:+.1%} ({direction}estimate)")

        # Confidence stats
        conf_stats = perf.get("stats_by_confidence", {})
        if conf_stats:
            print(f"\n  PERFORMANCE BY CONFIDENCE:")
            for conf in ["high", "medium", "low"]:
                if conf in conf_stats:
                    s = conf_stats[conf]
                    print(f"    {conf:<10} Brier: {s['brier']:.3f} | Hit: {s['hit_rate']:.0%} | "
                          f"Sim P&L: ${s['simulated_pnl']:+.2f} | N={s['count']}")

        # Direction stats
        dir_stats = perf.get("stats_by_direction", {})
        if dir_stats:
            print(f"\n  PERFORMANCE BY DIRECTION:")
            for d in ["yes", "no"]:
                if d in dir_stats:
                    s = dir_stats[d]
                    print(f"    {d.upper():<10} Brier: {s['brier']:.3f} | Hit: {s['hit_rate']:.0%} | N={s['count']}")

        # CLV stats
        clv_stats = perf.get("clv_stats")
        if clv_stats:
            print(f"\n  CLOSING LINE VALUE (CLV):")
            print(f"    Avg CLV:            {clv_stats['avg_clv']:+.1%}")
            print(f"    Positive CLV:       {clv_stats['positive_clv_pct']:.0%} of {clv_stats['count']} bets")
            clv_by_cat = perf.get("clv_by_category", {})
            if clv_by_cat:
                for cat, avg in sorted(clv_by_cat.items()):
                    print(f"    {cat:<20} {avg:+.1%}")

        # Brier trend by scan
        scan_stats = perf.get("stats_by_scan", {})
        if len(scan_stats) >= 2:
            print(f"\n  BRIER TREND BY SCAN:")
            for st, s in sorted(scan_stats.items()):
                scan_label = st[:16] if st and len(st) > 16 else (st or "unknown")
                print(f"    {scan_label}  Brier: {s['brier']:.3f} | Hit: {s['hit_rate']:.0%} | N={s['count']}")

            briers = [s["brier"] for _, s in sorted(scan_stats.items())]
            if len(briers) >= 3:
                recent_3 = briers[-3:]
                trend = " -> ".join(f"{b:.3f}" for b in recent_3)
                direction = "IMPROVING" if recent_3[-1] < recent_3[0] else "DETERIORATING"
                print(f"    Trend: {trend} ({direction})")

    # Bankroll trend
    if BANKROLL_FILE.exists():
        with open(BANKROLL_FILE) as f:
            history = json.load(f)
        if len(history) >= 2:
            print(f"\n  BANKROLL TREND:")
            for snap in history[-5:]:
                ts = snap["timestamp"][:16]
                print(f"    {ts}  Balance: ${snap['kalshi_total']:.2f} | "
                      f"P&L: ${snap['actual_pnl']:+.2f} | Brier: {snap['brier']:.3f}")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Check results and track performance")
    parser.add_argument("--stats", action="store_true", help="Show stats only (no API calls)")
    args = parser.parse_args()

    if args.stats:
        recs = load_json(RECS_FILE)
        bets = load_json(BETS_FILE)
        perf = load_json(PERF_FILE)
        if not isinstance(recs, list):
            recs = []
        if not isinstance(bets, list):
            bets = []
        print_stats(perf, recs, bets)
    else:
        asyncio.run(check_resolutions())


if __name__ == "__main__":
    main()
