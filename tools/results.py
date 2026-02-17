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
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend/ to import path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from services.kalshi import KalshiClient  # noqa: E402

RECS_FILE = DATA_DIR / "recommendations.json"
BETS_FILE = DATA_DIR / "bets.json"
PERF_FILE = DATA_DIR / "performance.json"
FEEDBACK_FILE = DATA_DIR / "calibration_feedback.txt"


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


async def check_resolutions() -> None:
    """Check Kalshi for resolved markets, update local tracking."""
    recs = load_json(RECS_FILE)
    bets = load_json(BETS_FILE)
    perf = load_json(PERF_FILE)

    if not isinstance(recs, list):
        recs = []
    if not isinstance(bets, list):
        bets = []

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
        print_stats(perf, recs, bets)
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
                }

                # Calculate simulated P&L
                edge = rec.get("edge", 0)
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

                print(f"      Bet P&L: ${bet['pnl']:+.2f} ({contracts} contracts)")

    if new_resolutions == 0:
        print("  No new resolutions found.")
    else:
        print(f"\n  {new_resolutions} market(s) resolved.")

    # Recalculate aggregate stats
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

        # Simulated P&L (all recommendations, $1 per contract)
        perf["simulated_pnl"] = round(
            sum(r.get("simulated_pnl_per_contract", 0) for r in resolved), 4
        )

        # Bias by category
        categories: dict[str, list[float]] = {}
        for r in resolved:
            cat = r.get("sport_type") or r.get("category", "Other")
            actual = 1.0 if r["outcome"] else 0.0
            bias = r["ai_estimate"] - actual
            categories.setdefault(cat, []).append(bias)

        perf["bias_by_category"] = {
            cat: round(sum(biases) / len(biases), 4)
            for cat, biases in categories.items()
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


def generate_feedback(perf: dict) -> None:
    """Write calibration_feedback.txt for use in future scans."""
    resolved = perf.get("resolved_markets", [])
    if not resolved:
        return

    lines = [
        f"CALIBRATION FEEDBACK (updated {perf.get('last_updated', 'unknown')}):",
        f"- Overall Brier: {perf.get('overall_brier', 0):.3f} (N={len(resolved)} markets). Target: <0.12",
        f"- Hit rate: {perf.get('hit_rate', 0):.0%} on {perf.get('total_recommended', 0)} recommended bets",
        f"- Total P&L: ${perf.get('total_pnl', 0):+.2f} (actual bets placed)",
    ]

    bias = perf.get("bias_by_category", {})
    for cat, avg_bias in sorted(bias.items()):
        if abs(avg_bias) < 0.03:
            lines.append(f"- {cat}: Well-calibrated ({avg_bias:+.0%} bias)")
        elif avg_bias > 0:
            lines.append(f"- {cat}: You OVERESTIMATE by ~{abs(avg_bias):.0%}. Lower your estimates.")
        else:
            lines.append(f"- {cat}: You UNDERESTIMATE by ~{abs(avg_bias):.0%}. Raise your estimates.")

    lines.append("Adjust your estimates accordingly in future research.")

    with open(FEEDBACK_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n  Calibration feedback saved to {FEEDBACK_FILE.relative_to(PROJECT_DIR)}")


def print_stats(perf: dict, recs: list, bets: list) -> None:
    """Print summary statistics."""
    resolved = perf.get("resolved_markets", [])
    active_recs = [r for r in recs if r.get("status") == "active"]
    open_bets = [b for b in bets if b.get("status") == "open"]
    closed_bets = [b for b in bets if b.get("status") == "closed"]

    print(f"\n{'='*50}")
    print(f"  PERFORMANCE SUMMARY")
    print(f"{'='*50}")
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

        bias = perf.get("bias_by_category", {})
        if bias:
            print(f"\n  BIAS BY CATEGORY:")
            for cat, avg in sorted(bias.items()):
                direction = "over" if avg > 0 else "under"
                print(f"    {cat:<15} {avg:+.1%} ({direction}estimate)")

    print(f"{'='*50}\n")


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
