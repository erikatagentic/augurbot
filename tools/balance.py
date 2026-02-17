#!/usr/bin/env python3
"""Check Kalshi account balance and open positions.

Usage:
    python3 tools/balance.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend/ to import path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import httpx  # noqa: E402
from services.kalshi import KalshiClient  # noqa: E402
from services.http_utils import request_with_retry  # noqa: E402


async def check_balance() -> None:
    client = KalshiClient()
    await client._ensure_auth()

    # Fetch balance
    path = "/trade-api/v2/portfolio/balance"
    headers = client._auth_headers("GET", path)
    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.get(
            f"{client.base_url}/portfolio/balance", headers=headers
        )
    bal = resp.json()
    cash = bal.get("balance", 0) / 100  # cents to dollars
    portfolio = bal.get("portfolio_value", 0) / 100

    print(f"\n{'='*50}")
    print(f"  KALSHI ACCOUNT")
    print(f"{'='*50}")
    print(f"  Cash balance:    ${cash:>10.2f}")
    print(f"  Portfolio value:  ${portfolio:>10.2f}")
    print(f"  Total:           ${cash + portfolio:>10.2f}")
    print(f"{'='*50}")

    # Fetch open positions
    positions = await client.fetch_positions()
    if not positions:
        print("\n  No open positions.\n")
        return

    print(f"\n  OPEN POSITIONS ({len(positions)})")
    print(f"  {'Ticker':<45} {'Side':<5} {'Qty':>5} {'Avg $':>7}")
    print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*7}")

    for pos in positions:
        ticker = pos.get("ticker", "?")
        # Kalshi returns market_exposure and total_traded
        yes_count = pos.get("market_exposure", 0)
        side = "YES" if yes_count > 0 else "NO"
        qty = abs(yes_count)
        # Try to get average price from the position data
        resting_count = pos.get("resting_orders_count", 0)
        print(f"  {ticker:<45} {side:<5} {qty:>5}")

    # Fetch resting orders
    resting = await client.fetch_orders(status="resting")
    if resting:
        print(f"\n  RESTING ORDERS ({len(resting)})")
        print(f"  {'Ticker':<45} {'Side':<5} {'Qty':>5} {'Price':>7}")
        print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*7}")
        for order in resting:
            ticker = order.get("ticker", "?")
            side = order.get("side", "?").upper()
            qty = order.get("remaining_count", order.get("count", 0))
            price = order.get("yes_price", 0)
            print(f"  {ticker:<45} {side:<5} {qty:>5} {price:>6}c")

    print()


def main():
    asyncio.run(check_balance())


if __name__ == "__main__":
    main()
