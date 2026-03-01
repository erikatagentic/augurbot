#!/usr/bin/env python3
"""Place a bet on Kalshi.

Usage:
    python3 tools/bet.py TICKER yes 50 65           # Market order (default): fills immediately
    python3 tools/bet.py TICKER no 25 40             # Market order for NO
    python3 tools/bet.py --limit TICKER yes 50 65    # Limit order: rests until filled
    python3 tools/bet.py --dry-run TICKER yes 50 65  # Verify auth without placing

Examples:
    python3 tools/bet.py KXNBAGAME-26FEB19DETNYK-DET yes 10 35
    python3 tools/bet.py KXEPLGAME-26MAR01CHELIV-CHE no 5 60
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add backend/ to import path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from services.kalshi import KalshiClient  # noqa: E402


async def place_bet(
    ticker: str,
    side: str,
    count: int,
    yes_price: int,
    dry_run: bool = False,
    market_order: bool = False,
) -> None:
    """Place an order on Kalshi."""
    client = KalshiClient()

    # Verify auth
    await client._ensure_auth()
    print(f"Authenticated with Kalshi (RSA-PSS)")

    order_type = "market" if market_order else "limit"
    cost_dollars = count * yes_price / 100 if side == "yes" else count * (100 - yes_price) / 100
    potential_win = count * (100 - yes_price) / 100 if side == "yes" else count * yes_price / 100

    print(f"\nOrder details:")
    print(f"  Ticker:    {ticker}")
    print(f"  Side:      {side.upper()}")
    print(f"  Contracts: {count}")
    print(f"  Type:      {order_type.upper()}")
    if order_type == "limit":
        print(f"  Price:     {yes_price}¢ (YES price)")
    else:
        print(f"  Price:     MARKET (best available)")
    print(f"  Est. Cost: ${cost_dollars:.2f}")
    print(f"  Potential: ${potential_win:.2f} profit if correct")

    if dry_run:
        print(f"\n  [DRY RUN] Order not placed.")
        return

    result = await client.place_order(
        ticker=ticker,
        side=side,
        count=count,
        yes_price=yes_price,
        order_type=order_type,
    )

    order_id = result.get("order", {}).get("order_id", "unknown")
    status = result.get("order", {}).get("status", "unknown")
    print(f"\n  Order placed! ID: {order_id} | Status: {status}")


def main():
    parser = argparse.ArgumentParser(description="Place a bet on Kalshi")
    parser.add_argument("ticker", help="Market ticker (e.g., KXNBAGAME-26FEB19DETNYK-DET)")
    parser.add_argument("side", choices=["yes", "no"], help="yes or no")
    parser.add_argument("count", type=int, help="Number of contracts")
    parser.add_argument("price", type=int, help="YES price in cents (1-99)")
    parser.add_argument("--dry-run", action="store_true", help="Verify auth without placing order")
    parser.add_argument("--market", action="store_true", help="Place market order (fills immediately at best price)")
    parser.add_argument("--limit", action="store_true", help="Place limit order (rests until filled or expired)")
    args = parser.parse_args()

    if not 1 <= args.price <= 99:
        print("Error: price must be between 1 and 99 cents")
        sys.exit(1)
    if args.count < 1:
        print("Error: count must be at least 1")
        sys.exit(1)

    # Default to market orders unless --limit is explicitly passed
    use_market = not args.limit

    asyncio.run(
        place_bet(
            ticker=args.ticker,
            side=args.side,
            count=args.count,
            yes_price=args.price,
            dry_run=args.dry_run,
            market_order=use_market,
        )
    )


if __name__ == "__main__":
    main()
