#!/usr/bin/env python3
"""Fetch Kalshi markets and output JSON for Claude Code analysis.

Usage:
    python3 tools/scan.py                     # Default: 48h window, all categories
    python3 tools/scan.py --hours 72          # Custom time window
    python3 tools/scan.py --categories sports # Sports only

Output: data/latest_scan.json + summary table to stdout.
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend/ to import path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.chdir(BACKEND_DIR)  # So .env is found by pydantic-settings

from services.kalshi import KalshiClient  # noqa: E402


# ── Deduplication (same logic as scanner.py) ──


def _deduplicate_event_markets(market_list: list[dict]) -> list[dict]:
    """Keep one market per event — skip binary complements."""
    groups: dict[str, list[dict]] = defaultdict(list)
    no_event: list[dict] = []

    for m in market_list:
        et = m.get("event_ticker", "")
        if et:
            groups[et].append(m)
        else:
            no_event.append(m)

    result: list[dict] = list(no_event)
    deduped = 0

    for _et, markets in groups.items():
        if len(markets) <= 1:
            result.extend(markets)
            continue
        best = max(
            markets,
            key=lambda m: (
                m.get("volume", 0),
                -abs(m.get("price_yes", 0.5) - 0.5),
            ),
        )
        result.append(best)
        deduped += len(markets) - 1

    if deduped:
        print(f"  Deduplicated {deduped} complement markets")

    return result


# ── Date filtering (same logic as scanner.py) ──


def _filter_by_date(
    market_list: list[dict], max_hours: int
) -> list[dict]:
    """Filter markets by game date (sports) or close date (econ)."""
    now = datetime.now(timezone.utc)
    today_utc = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = now + timedelta(hours=max_hours)

    filtered = []
    for m in market_list:
        is_sport = bool(m.get("sport_type"))
        game_date_str = m.get("game_date")

        if is_sport and game_date_str:
            try:
                game_dt = datetime.fromisoformat(game_date_str)
                if game_dt < today_utc or game_dt > window_end:
                    continue
            except (ValueError, TypeError):
                pass  # Keep if unparseable
        elif is_sport:
            pass  # Sport without game date — keep
        else:
            close_str = m.get("close_date")
            if close_str:
                try:
                    close_dt = datetime.fromisoformat(
                        close_str.replace("Z", "+00:00")
                    )
                    cat = (m.get("category") or "").lower()
                    max_close = now + timedelta(days=30 if cat == "economics" else 0, hours=0 if cat == "economics" else max_hours)
                    if close_dt < now or close_dt > max_close:
                        continue
                except (ValueError, TypeError):
                    pass

        filtered.append(m)

    return filtered


# ── Main ──


async def fetch_markets(
    max_hours: int = 48,
    categories: set[str] | None = None,
    all_categories: bool = False,
) -> list[dict]:
    """Fetch, filter, and deduplicate Kalshi markets.

    By default applies the basketball+economics focus filter. Pass
    all_categories=True to keep every category (for cross-category paper
    discovery — finding out where, if anywhere, we have an edge).
    """
    if categories is None:
        categories = {"sports", "economics"}

    now = datetime.now(timezone.utc)
    min_close_ts = int(now.timestamp())
    max_close_ts = int((now + timedelta(days=30)).timestamp())

    client = KalshiClient()

    print(f"Fetching markets from Kalshi ({', '.join(categories)})...")
    markets = await client.fetch_markets(
        limit=100,
        min_volume=10000.0,
        categories=categories,
        min_close_ts=min_close_ts,
        max_close_ts=max_close_ts,
    )
    print(f"  Raw: {len(markets)} markets from API")

    # Filter by date
    markets = _filter_by_date(markets, max_hours)
    print(f"  After date filter ({max_hours}h window): {len(markets)}")

    # Deduplicate binary complements
    markets = _deduplicate_event_markets(markets)
    print(f"  Final: {len(markets)} markets")

    # Skip extreme prices
    markets = [
        m for m in markets
        if 0.02 < m.get("price_yes", 0) < 0.98
    ]

    # All-categories mode: skip the focus filter entirely (paper discovery).
    if all_categories:
        print(f"  All-categories mode: {len(markets)} markets (focus filter OFF)")
        return markets

    # Focus filter: basketball + economics + UCL soccer only
    # Based on performance data: NBA Brier 0.150, NCAA 0.189 (good)
    # Tennis 0.273 (dropped), domestic soccer 0.251 (dropped)
    focused = []
    dropped_cats: dict[str, int] = defaultdict(int)
    for m in markets:
        sport = (m.get("sport_type") or "").lower()
        ticker = m.get("platform_id", "")
        cat = (m.get("category") or "").lower()

        if cat == "economics":
            focused.append(m)
        elif sport in ("nba", "ncaa basketball"):
            focused.append(m)
        elif sport == "soccer" and "UCL" in ticker.upper():
            focused.append(m)
        else:
            dropped_cats[sport or cat] += 1

    if dropped_cats:
        dropped_summary = ", ".join(f"{v} {k}" for k, v in sorted(dropped_cats.items()))
        print(f"  Focus filter dropped: {dropped_summary}")

    return focused


def print_summary(markets: list[dict], show_prices: bool = False) -> None:
    """Print a summary table to stdout.

    BLIND BY DEFAULT: prices are hidden so the researching agent is not anchored
    by the market line (the core blind-estimation rule). Prices are still saved
    to latest_scan.json for the reveal step. Pass show_prices=True only after
    estimates are locked.
    """
    if not markets:
        print("\nNo markets found.")
        return

    sports = [m for m in markets if m.get("sport_type")]
    econ = [m for m in markets if m.get("economic_indicator")]
    other = [m for m in markets if not m.get("sport_type") and not m.get("economic_indicator")]

    print(f"\n{'='*80}")
    print(f"SCAN RESULTS — {len(markets)} markets ({len(sports)} sports, {len(econ)} economics)")
    print(f"{'='*80}\n")

    for i, m in enumerate(markets, 1):
        cat = m.get("sport_type") or m.get("economic_indicator") or "Other"
        price = m.get("price_yes", 0)
        label = m.get("outcome_label", "")
        question = m.get("question", "")[:70]

        date_str = ""
        if m.get("game_date"):
            try:
                gd = datetime.fromisoformat(m["game_date"])
                date_str = gd.strftime("%b %d")
            except (ValueError, TypeError):
                pass
        elif m.get("close_date"):
            try:
                cd = datetime.fromisoformat(m["close_date"].replace("Z", "+00:00"))
                date_str = cd.strftime("%b %d")
            except (ValueError, TypeError):
                pass

        price_str = f"Price: {price:.0%}" if show_prices else "[price hidden — blind]"
        print(f"  {i:2d}. [{cat:<10}] {question}")
        if label:
            print(f"      Outcome: {label} | {price_str} | Date: {date_str}")
        else:
            print(f"      {price_str} | Date: {date_str}")
        print()


def save_results(markets: list[dict], output_path: Path) -> None:
    """Save markets to JSON, stripping prices for the blind research phase."""
    # Save full data (with prices) for EV calculation later
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(
            {
                "scan_time": datetime.now(timezone.utc).isoformat(),
                "market_count": len(markets),
                "markets": markets,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"\nSaved to {output_path}")

    # Also save a blind version (no prices) for Claude Code research
    blind_path = output_path.parent / "blind_markets.json"
    blind_markets = []
    for m in markets:
        # Compute liquidity tier from volume and bid-ask spread
        # Does NOT reveal the price — only signals market quality
        volume = m.get("volume", 0)
        yes_bid = m.get("yes_bid", 0)
        yes_ask = m.get("yes_ask", 0)
        spread = abs(yes_ask - yes_bid) if yes_bid > 0 and yes_ask > 0 else 1.0
        if volume > 100_000 and spread < 0.05:
            liquidity_tier = "high"
        elif volume > 50_000 or spread < 0.10:
            liquidity_tier = "medium"
        else:
            liquidity_tier = "low"

        blind_markets.append({
            "ticker": m.get("platform_id", ""),
            "question": m.get("question", ""),
            "category": m.get("category", ""),
            "sport_type": m.get("sport_type"),
            "economic_indicator": m.get("economic_indicator"),
            "close_date": m.get("close_date", ""),
            "game_date": m.get("game_date"),
            "outcome_label": m.get("outcome_label"),
            "liquidity_tier": liquidity_tier,
        })
    with open(blind_path, "w") as f:
        json.dump(blind_markets, f, indent=2, default=str)
    print(f"Blind markets (no prices) saved to {blind_path}")

    # Archive
    archive_dir = output_path.parent / "scans"
    archive_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    archive_path = archive_dir / f"{date_str}.json"
    with open(archive_path, "w") as f:
        json.dump(
            {
                "scan_time": datetime.now(timezone.utc).isoformat(),
                "market_count": len(markets),
                "markets": markets,
            },
            f,
            indent=2,
            default=str,
        )


def main():
    parser = argparse.ArgumentParser(description="Fetch Kalshi markets for Claude Code analysis")
    parser.add_argument("--hours", type=int, default=48, help="Time window in hours (default: 48)")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=["sports", "economics"],
        help="Categories to scan (default: sports economics)",
    )
    parser.add_argument(
        "--show-prices",
        action="store_true",
        help="Reveal market prices in the summary (default: hidden to keep "
        "research blind). Use only after estimates are locked.",
    )
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="Keep every category (skip the basketball+economics focus "
        "filter) for cross-category paper discovery.",
    )
    args = parser.parse_args()

    markets = asyncio.run(
        fetch_markets(
            max_hours=args.hours,
            categories=set(args.categories),
            all_categories=args.all_categories,
        )
    )

    print_summary(markets, show_prices=args.show_prices)

    output_path = Path(__file__).resolve().parent.parent / "data" / "latest_scan.json"
    save_results(markets, output_path)


if __name__ == "__main__":
    main()
