#!/usr/bin/env python3
"""Check current market prices on open positions and calculate unrealized P&L.

Usage:
    python3 tools/positions.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import httpx  # noqa: E402
from services.kalshi import KalshiClient, _best_price_cents  # noqa: E402
from services.http_utils import request_with_retry  # noqa: E402

BETS_FILE = DATA_DIR / "bets.json"


def load_bets() -> list[dict]:
    if not BETS_FILE.exists():
        return []
    with open(BETS_FILE) as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


async def _fetch_current_price(client: KalshiClient, ticker: str) -> int:
    """Fetch current YES price in cents for a market ticker. Returns 0 on error."""
    try:
        await client._ensure_auth()
        path = f"/trade-api/v2/markets/{ticker}"
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await request_with_retry(
                http, "GET",
                f"{client.base_url}/markets/{ticker}",
                headers=client._auth_headers("GET", path),
            )
        market = resp.json().get("market", resp.json())
        return _best_price_cents(market)
    except Exception:
        return 0


async def check_positions() -> None:
    client = KalshiClient()

    bets = load_bets()
    open_bets = {b["ticker"]: b for b in bets if b.get("status") == "open"}

    if not open_bets:
        print("\nNo open bets to check.")
        return

    # Fetch current prices
    print(f"\nFetching prices for {len(open_bets)} open bet(s)...")
    current_prices: dict[str, int] = {}
    for ticker in open_bets:
        current_prices[ticker] = await _fetch_current_price(client, ticker)

    # Display
    print(f"\n{'='*70}")
    print(f"  OPEN POSITIONS — Mark-to-Market")
    print(f"{'='*70}")
    print(f"  {'Market':<35} {'Dir':>4} {'Entry':>6} {'Now':>6} {'Move':>7} {'P&L':>8} {'Flag'}")
    print(f"  {'-'*35} {'-'*4} {'-'*6} {'-'*6} {'-'*7} {'-'*8} {'-'*10}")

    total_unrealized = 0.0
    alerts: list[str] = []

    for ticker in sorted(open_bets):
        bet = open_bets[ticker]
        current_cents = current_prices.get(ticker, 0)
        current_pct = current_cents / 100 if current_cents else 0

        entry_cents = bet["yes_price"]
        entry_pct = entry_cents / 100
        direction = bet["direction"]
        contracts = bet["contracts"]
        question = bet.get("question", ticker)
        # Truncate question for display
        label = question[:35] if len(question) > 35 else question

        if current_cents == 0:
            print(f"  {label:<35} {direction.upper():>4} {entry_cents:>5}c   n/a     n/a      n/a  NO PRICE")
            continue

        # Calculate move and unrealized P&L
        move = current_pct - entry_pct
        if direction == "yes":
            unrealized = contracts * (current_pct - entry_pct)
        else:
            unrealized = contracts * (entry_pct - current_pct)

        total_unrealized += unrealized

        # Flags
        flag = ""
        favorable_move = move if direction == "yes" else -move
        if favorable_move >= 0.10:
            flag = "CASH OUT?"
            alerts.append(f"  {question}: Line moved {abs(favorable_move):.0%} in your favor")
        elif favorable_move <= -0.10:
            flag = "CUT LOSS?"
            alerts.append(f"  {question}: Line moved {abs(favorable_move):.0%} against you")

        print(f"  {label:<35} {direction.upper():>4} {entry_cents:>5}c {current_cents:>5}c "
              f"{move:>+6.0%} ${unrealized:>+7.2f} {flag}")

    print(f"  {'-'*70}")
    print(f"  Total unrealized P&L: ${total_unrealized:+.2f}")
    print(f"{'='*70}")

    if alerts:
        print(f"\n  ALERTS:")
        for alert in alerts:
            print(alert)

    print()


def main():
    asyncio.run(check_positions())


if __name__ == "__main__":
    main()
