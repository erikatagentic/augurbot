#!/usr/bin/env python3
"""Paper-mode cross-venue arbitrage scanner (Kalshi <-> Polymarket).

READ-ONLY. Fetches live markets from both venues, structurally matches the
same-event pairs, computes the fee-net arb edge, prints opportunities, and
appends a paper-trade ledger to data/arb_paper.jsonl. NO orders are placed.

Rule F: prints the confirmed same-event pair count every run. A near-zero
count means the addressable arb surface has dried up — stop, don't fire.

Usage:
    backend/.venv/bin/python3 tools/arb_scan.py
    backend/.venv/bin/python3 tools/arb_scan.py --min-edge 0.02 --kalshi-min-volume 2000
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from config import settings  # noqa: E402
from services.kalshi import KalshiClient  # noqa: E402
from services.polymarket import PolymarketClient  # noqa: E402
from services.arb_matcher import match_markets  # noqa: E402
from services.arb_detector import detect_arb  # noqa: E402

GAMMA = settings.polymarket_gamma_url


def _f(v, default=None):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


async def fetch_polymarket(min_volume: float, pages: int = 8) -> list[dict]:
    """Fetch raw Gamma markets (with outcomePrices midpoints) — no CLOB loop."""
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as c:
        for i in range(pages):
            params = {
                "limit": 100, "offset": i * 100, "closed": "false",
                "order": "volume", "ascending": "false",
                "volume_num_min": min_volume,
            }
            r = await c.get(f"{GAMMA}/markets", params=params)
            page = r.json()
            if not page:
                break
            out.extend(page)
            if len(page) < 100:
                break
    return out


async def fetch_kalshi(min_volume: float) -> list[dict]:
    client = KalshiClient()
    return await client.fetch_markets(
        min_volume=min_volume, categories={"sports"}
    )


def poly_prices(pm: dict) -> list[float] | None:
    raw = pm.get("outcomePrices")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, list) or len(raw) != 2:
        return None
    a, b = _f(raw[0]), _f(raw[1])
    return [a, b] if a is not None and b is not None else None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-edge", type=float, default=0.02,
                    help="Minimum fee-net edge to flag (default 0.02 = 2c/contract)")
    ap.add_argument("--kalshi-min-volume", type=float, default=2000.0)
    ap.add_argument("--poly-min-volume", type=float, default=2000.0)
    args = ap.parse_args()

    print("Fetching live markets...")
    kalshi, poly = await asyncio.gather(
        fetch_kalshi(args.kalshi_min_volume),
        fetch_polymarket(args.poly_min_volume),
    )
    print(f"  Kalshi sports markets:  {len(kalshi)}")
    print(f"  Polymarket markets:     {len(poly)}")

    # Index Polymarket by conditionId for price lookup post-match.
    poly_by_cid = {pm.get("conditionId", ""): pm for pm in poly}

    pairs = match_markets(kalshi, poly)
    print(f"\n=== CONFIRMED SAME-EVENT PAIRS (Rule F): {len(pairs)} ===")
    if not pairs:
        print("  No same-event pairs today. Nothing to arb — stopping.")
        return

    kalshi_by_ticker = {
        (m.get("ticker") or m.get("platform_id", "")): m for m in kalshi
    }
    pc = PolymarketClient()

    opportunities = []
    for p in pairs:
        km = kalshi_by_ticker.get(p.kalshi_ticker)
        pm = poly_by_cid.get(p.poly_condition_id)
        if not km or not pm:
            continue
        k_ask = _f(km.get("yes_ask"))
        k_bid = _f(km.get("yes_bid"))
        prices = poly_prices(pm)
        if k_ask is None or k_bid is None or prices is None:
            continue
        subj_price = prices[p.poly_subject_index]
        other_price = prices[1 - p.poly_subject_index]

        # Midpoint screen (optimistic — Gamma midpoints).
        mid = detect_arb(
            kalshi_yes_ask=k_ask, kalshi_yes_bid=k_bid,
            poly_subject_price=subj_price, poly_other_price=other_price,
            threshold=args.min_edge,
        )

        # Re-price against the LIVE CLOB book — executable asks are what we
        # actually pay. This is the real test; midpoints flatter the edge.
        exec_result = None
        subj_book = other_book = None
        toks = p.poly_token_ids
        if len(toks) == 2:
            subj_book, other_book = await asyncio.gather(
                pc.fetch_order_book(toks[p.poly_subject_index]),
                pc.fetch_order_book(toks[1 - p.poly_subject_index]),
            )
            if subj_book and other_book:
                exec_result = detect_arb(
                    kalshi_yes_ask=k_ask, kalshi_yes_bid=k_bid,
                    poly_subject_price=subj_book["best_ask"],
                    poly_other_price=other_book["best_ask"],
                    threshold=args.min_edge,
                )

        decision = exec_result or mid
        tag = "executable" if exec_result else "midpoint-only"
        book_line = (
            f"\n    Poly    book ask subj/other: "
            f"{subj_book['best_ask']:.2f}/{other_book['best_ask']:.2f}"
            if exec_result else ""
        )
        exec_line = (
            f"  |  EXECUTABLE edge: {exec_result['best_edge']:+.3f}"
            if exec_result else "  (book unavailable)"
        )
        print(
            f"\n  {p.kalshi_subject}  (conf {p.confidence:.0%})"
            f"\n    Kalshi  YES bid/ask: {k_bid:.2f}/{k_ask:.2f}"
            f"\n    Poly    midpoint subj/other: {subj_price:.2f}/{other_price:.2f}"
            f"{book_line}"
            f"\n    midpoint edge: {mid['best_edge']:+.3f}{exec_line}"
            f"  ({decision['direction']})  "
            f"{'>> ARB' if decision['has_arb'] else 'no edge'}  [{tag}]"
        )
        if decision["has_arb"]:
            opportunities.append({
                "subject": p.kalshi_subject,
                "kalshi_ticker": p.kalshi_ticker,
                "poly_condition_id": p.poly_condition_id,
                "kalshi_yes_bid": k_bid, "kalshi_yes_ask": k_ask,
                "poly_midpoint_subject": subj_price,
                "poly_midpoint_other": other_price,
                "priced_on": tag,
                **decision,
            })

    # Dedup mirror legs of the same event (same Poly market) — keep best edge.
    best_by_event: dict[str, dict] = {}
    for o in opportunities:
        cid = o["poly_condition_id"]
        if cid not in best_by_event or o["best_edge"] > best_by_event[cid]["best_edge"]:
            best_by_event[cid] = o
    opportunities = list(best_by_event.values())

    print(f"\n=== ARB CANDIDATES (edge > {args.min_edge}, "
          f"deduped by event): {len(opportunities)} ===")
    print("  NOTE: edges are off Polymarket midpoints, not the live CLOB book. "
          "These are CANDIDATES to verify against both order books before any "
          "live fire (B5), not confirmed locked profit.")

    # Append paper ledger.
    stamp = datetime.now(timezone.utc).isoformat()
    ledger = DATA_DIR / "arb_paper.jsonl"
    with open(ledger, "a") as f:
        for o in opportunities:
            f.write(json.dumps({"ts": stamp, **o}) + "\n")
    if opportunities:
        print(f"  Wrote {len(opportunities)} paper opportunities -> {ledger}")
    else:
        print("  No fee-net arb today (venues agree within fees). "
              "This is the expected default on an efficient day.")


if __name__ == "__main__":
    asyncio.run(main())
