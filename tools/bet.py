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
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend/ to import path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from config import settings  # noqa: E402
from services.kalshi import KalshiClient  # noqa: E402
from services.risk_guard import kill_switch_active, pre_trade_check  # noqa: E402


def _load_json(path: Path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _kalshi_book_cents(market: dict) -> dict:
    """Extract {yes_bid, yes_ask} in cents from a live Kalshi market dict.

    Handles the 2026 schema (yes_bid_dollars / yes_ask_dollars as string
    dollars, e.g. "0.4100") and the legacy cent-integer schema.
    """
    def pick(dollars_key: str, cents_key: str):
        if market.get(dollars_key) is not None:
            try:
                return round(float(market[dollars_key]) * 100)
            except (ValueError, TypeError):
                return None
        v = market.get(cents_key)
        try:
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    return {
        "yes_bid": pick("yes_bid_dollars", "yes_bid"),
        "yes_ask": pick("yes_ask_dollars", "yes_ask"),
    }


async def place_bet(
    ticker: str,
    side: str,
    count: int,
    yes_price: int,
    dry_run: bool = False,
    market_order: bool = False,
    force: bool = False,
) -> None:
    """Place an order on Kalshi."""
    client = KalshiClient()

    # Kill switch is absolute — halt before any auth or network call.
    if kill_switch_active(REPO_ROOT):
        print("Kill switch active (STOP file at repo root). All orders halted. "
              "Remove the STOP file to resume.")
        return

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

    # ── Pre-trade risk guard (deterministic; see services/risk_guard.py) ──
    bal = await client.fetch_balance()
    live_mkt = await client.fetch_market(ticker)
    live_book = _kalshi_book_cents(live_mkt) if live_mkt else None
    bets = _load_json(DATA_DIR / "bets.json", [])
    history = _load_json(DATA_DIR / "bankroll_history.json", [])

    risk = pre_trade_check(
        repo_root=REPO_ROOT,
        ticker=ticker,
        side=side,
        count=count,
        intended_yes_price=yes_price,
        cash=bal["cash"],
        total=bal["total"],
        bets=bets,
        bankroll_history=history,
        live_book=live_book,
        daily_loss_limit_fraction=settings.daily_loss_limit_fraction,
        max_drawdown_halt_fraction=settings.max_drawdown_halt_fraction,
        max_open_positions=settings.max_open_positions,
        max_exposure_fraction=settings.max_exposure_fraction,
        max_event_exposure_fraction=settings.max_event_exposure_fraction,
        max_single_bet_fraction=settings.max_single_bet_fraction,
        slippage_tolerance=settings.slippage_tolerance,
        max_spread_cents=settings.max_spread_cents,
        today=datetime.now(timezone.utc).date(),
    )
    print(f"\n  Account: cash ${bal['cash']:.2f} | total ${bal['total']:.2f}")
    print(risk.render())

    if not risk.allowed:
        if risk.kill_switch:
            print("\n  Kill switch is absolute — order refused. "
                  "Remove the STOP file to resume.")
            return
        if not force:
            print("\n  Order refused by risk guard. Pass --force to override "
                  "soft checks (kill switch can never be overridden).")
            return
        print("\n  --force given: overriding soft risk blocks.")

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
    parser.add_argument("--force", action="store_true", help="Override soft risk-guard blocks (kill switch can never be overridden)")
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
            force=args.force,
        )
    )


if __name__ == "__main__":
    main()
