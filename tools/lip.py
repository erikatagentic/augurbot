"""Shared helpers for the Kalshi Liquidity-Incentive-Program (LIP) tooling.

Phase 0 recon, Phase 1 observation (`book_observe.py`), and Phase 2 live
market-making (`lip_make.py`) all hit the same three endpoints:

  GET /trade-api/v2/incentive_programs?status=active&type=liquidity
  GET /trade-api/v2/markets?tickers=...
  GET /trade-api/v2/markets/{ticker}/orderbook

This module wraps those (reusing `KalshiClient` RSA-PSS signing) and parses the
quirky response shapes verified live 2026-06-29:
  - prices are STRINGS in dollars: yes_bid_dollars="0.1000"
  - orderbook is under key "orderbook_fp" with "yes_dollars"/"no_dollars",
    each a list of [price_str, size_str]
  - period_reward is in centi-cents (/10000 = dollars)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.kalshi import KalshiClient  # noqa: E402


def load_client() -> KalshiClient:
    """Return an authed KalshiClient. Chdir to backend/ so pydantic-settings
    finds backend/.env (model_config env_file is relative). CLI entrypoints
    should call this; data paths in the tools are absolute so chdir is safe."""
    os.chdir(BACKEND_DIR)
    return KalshiClient()


def _f(x) -> float | None:
    """Coerce Kalshi's string numerics to float; None on failure."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _get(client: KalshiClient, sub_path: str, params: dict | None = None) -> httpx.Response:
    """Signed GET. `sub_path` is the path AFTER /trade-api/v2, e.g.
    '/incentive_programs' or '/markets/KXFOO/orderbook'."""
    full_path = f"/trade-api/v2{sub_path}"
    headers = client._auth_headers("GET", full_path)
    url = f"{client.base_url}{sub_path}"
    with httpx.Client(timeout=30.0) as c:
        return c.get(url, params=params or {}, headers=headers)


def fetch_liquidity_programs(client: KalshiClient, max_pages: int = 30) -> list[dict]:
    """All active liquidity incentive programs, paginated.

    Each returned dict adds parsed convenience fields: pool_usd, period_days,
    pool_per_day, target_size (contracts).
    """
    from datetime import datetime

    def parse_dt(s: str):
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    out: list[dict] = []
    cursor: str | None = None
    for _ in range(max_pages):
        params = {"status": "active", "type": "liquidity", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = _get(client, "/incentive_programs", params)
        r.raise_for_status()
        data = r.json()
        batch = data.get("incentive_programs", [])
        for p in batch:
            try:
                days = (parse_dt(p["end_date"]) - parse_dt(p["start_date"])).total_seconds() / 86400
            except (KeyError, ValueError, TypeError):
                days = None
            pool = (p.get("period_reward", 0) or 0) / 10000.0
            p["pool_usd"] = pool
            p["period_days"] = days
            p["pool_per_day"] = (pool / days) if days else None
            p["target_size"] = _f(p.get("target_size_fp")) or 0.0
            out.append(p)
        cursor = data.get("next_cursor")
        if not cursor or not batch:
            break
    return out


def fetch_market_prices(client: KalshiClient, tickers: list[str]) -> dict[str, dict]:
    """Batch best bid/ask + best-level resting size for each ticker."""
    out: dict[str, dict] = {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i + 100]
        r = _get(client, "/markets", {"tickers": ",".join(batch), "limit": 1000})
        if r.status_code != 200:
            continue
        for m in r.json().get("markets", []):
            out[m.get("ticker")] = {
                "yes_bid": _f(m.get("yes_bid_dollars")),
                "yes_ask": _f(m.get("yes_ask_dollars")),
                "no_bid": _f(m.get("no_bid_dollars")),
                "no_ask": _f(m.get("no_ask_dollars")),
                "yes_bid_size": _f(m.get("yes_bid_size_fp")) or 0.0,
                "no_bid_size": _f(m.get("no_bid_size_fp")) or 0.0,
                "volume": _f(m.get("volume_fp")) or 0.0,
                "volume_24h": _f(m.get("volume_24h_fp")) or 0.0,
                "status": m.get("status"),
            }
    return out


def fetch_orderbook(client: KalshiClient, ticker: str) -> dict | None:
    """Parsed orderbook: {'yes': [(price,size),...], 'no': [...]} sorted by
    price descending (best bid first). None on failure."""
    r = _get(client, f"/markets/{ticker}/orderbook", {"depth": 100})
    if r.status_code != 200:
        return None
    ob = r.json().get("orderbook_fp") or {}
    out = {}
    for side, key in (("yes", "yes_dollars"), ("no", "no_dollars")):
        levels = ob.get(key) or []
        parsed = [(_f(p), _f(s)) for p, s in levels]
        parsed = [(p, s) for p, s in parsed if p is not None and s is not None]
        parsed.sort(key=lambda x: -x[0])  # best (highest bid) first
        out[side] = parsed
    return out


def qualifying_score(
    levels: list[tuple[float, float]], target_size: float, discount_factor: float
) -> tuple[float, bool, float | None]:
    """Kalshi LIP qualifying score for one side, per the CFTC filing.

    Walk the book from the best (Reference) price inward, including the FULL size
    at each level, until cumulative size >= target_size. Each included level
    scores discount_factor^N * size, where N = ticks (cents) from best. If the
    book runs out before reaching target_size, the side does NOT qualify and
    Kalshi clears it (score 0) — this is what makes a snapshot one-sided.

    Returns (total_score, reached_target, best_price).
    """
    if not levels:
        return 0.0, False, None
    best = levels[0][0]
    cum = 0.0
    score = 0.0
    for price, size in levels:
        n = round((best - price) / 0.01)  # ticks from best (1 tick = 1c)
        score += (discount_factor ** n) * size
        cum += size
        if cum >= target_size:
            return score, True, best
    return 0.0, False, best  # never reached target -> side cleared


def our_share(existing_score: float, our_size: float) -> float:
    """Our per-snapshot normalized score if we rest `our_size` at the best price
    (N=0, full credit). existing_score is the qualifying score from everyone
    else on that side."""
    denom = existing_score + our_size
    return (our_size / denom) if denom > 0 else 0.0
