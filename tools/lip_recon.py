#!/usr/bin/env python3
"""LIP Phase 0 — recon + Phase 1 candidate selection.

Pulls every active liquidity incentive program, finds the ones whose qualifying
size we can fund within a budget, and (for the shortlist) fetches the real
orderbook to compute an HONEST rebate upper bound — qualifying liquidity is the
full in-band resting depth, NOT just the best level. Writes the shortlist to
data/lip_candidates.json for book_observe.py.

CAUTION: the rebate number here is an UPPER BOUND. It assumes we capture our
size-share of the pool and ignores adverse selection entirely. The real net is
what Phase 1 (book_observe.py) and Phase 2 (lip_make.py) measure.

Usage:
    backend/.venv/bin/python3 tools/lip_recon.py
    backend/.venv/bin/python3 tools/lip_recon.py --budget 130 --band 0.02 --top 15
"""
import argparse
import json
import statistics as st
from pathlib import Path

from lip import (
    fetch_liquidity_programs,
    fetch_market_prices,
    fetch_orderbook,
    load_client,
    our_share,
    qualifying_score,
)

DATA = Path(__file__).resolve().parent.parent / "data"


def cheapest_side(pr: dict) -> tuple[str, float, float] | None:
    """(side, price, best_level_size) for the cheaper side to post a resting bid."""
    sides = []
    if pr.get("yes_bid"):
        sides.append(("yes", pr["yes_bid"], pr.get("yes_bid_size", 0.0)))
    if pr.get("no_bid"):
        sides.append(("no", pr["no_bid"], pr.get("no_bid_size", 0.0)))
    if not sides:
        return None
    return min(sides, key=lambda s: s[1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=130.0, help="Capital available (USD)")
    ap.add_argument("--min-pool-day", type=float, default=2.0, help="Min pool $/day to bother")
    ap.add_argument("--top", type=int, default=15, help="How many shortlist candidates to deep-probe + save")
    args = ap.parse_args()

    client = load_client()
    progs = fetch_liquidity_programs(client)
    print(f"Active liquidity programs: {len(progs)}")

    days = [p["period_days"] for p in progs if p["period_days"]]
    poolday = [p["pool_per_day"] for p in progs if p["pool_per_day"]]
    print(f"  period days: min {min(days):.2f} / median {st.median(days):.2f} / max {max(days):.2f}")
    print(f"  pool $/day:  min {min(poolday):.1f} / median {st.median(poolday):.1f} / max {max(poolday):.1f}")
    print(f"  target_size_fp values: {sorted({p['target_size'] for p in progs})}")

    # Prices for affordability + quality filter
    tickers = [p["market_ticker"] for p in progs if p.get("market_ticker")]
    prices = fetch_market_prices(client, tickers)

    affordable = []
    for p in progs:
        pr = prices.get(p.get("market_ticker"))
        if not pr:
            continue
        cs = cheapest_side(pr)
        if not cs:
            continue
        side, price, _ = cs
        cap = p["target_size"] * price
        if cap > args.budget:
            continue
        if (p["pool_per_day"] or 0) < args.min_pool_day:
            continue
        affordable.append({
            "ticker": p["market_ticker"], "side": side, "price": round(price, 4),
            "cap_usd": round(cap, 1), "target_size": p["target_size"],
            "pool_usd": round(p["pool_usd"], 1), "period_days": round(p["period_days"], 2) if p["period_days"] else None,
            "pool_per_day": round(p["pool_per_day"], 2), "end_date": p.get("end_date"),
            "volume_24h": pr.get("volume_24h", 0.0),
            "discount_factor_bps": p.get("discount_factor_bps"),
            "discount_factor": (p.get("discount_factor_bps") or 5000) / 10000.0,
        })

    # Quality shortlist for OBSERVATION: real recent volume, non-penny, multi-day window.
    quality = [
        a for a in affordable
        if a["volume_24h"] >= 50 and 0.04 <= a["price"] <= 0.96 and (a["period_days"] or 0) >= 1.0
    ]
    quality.sort(key=lambda a: -a["pool_per_day"])
    print(f"\nAffordable within ${args.budget:.0f}: {len(affordable)}  |  quality observation candidates: {len(quality)}")

    # Deep-probe: real discount-weighted qualifying score (CFTC formula) + two-sided gate.
    # We post target_size at best (N=0). two_sided requires the OTHER side to reach
    # target_size from existing depth (we don't quote it); if not, snapshots are void.
    shortlist = []
    for a in quality[:args.top]:
        ob = fetch_orderbook(client, a["ticker"])
        if not ob:
            continue
        disc = a["discount_factor"]
        our_levels = ob[a["side"]]
        other_levels = ob["no" if a["side"] == "yes" else "yes"]
        existing_score, _, _ = qualifying_score(our_levels, a["target_size"], disc)
        _, other_reached, _ = qualifying_score(other_levels, a["target_size"], disc)
        share = our_share(existing_score, a["target_size"])
        a["existing_score"] = round(existing_score, 0)
        a["two_sided"] = bool(other_reached)
        a["ub_share"] = round(share, 3)
        # void (no reward) when the market isn't two-sided at this snapshot
        a["ub_rebate_day"] = round(share * a["pool_per_day"] * (1 if other_reached else 0), 2)
        shortlist.append(a)

    shortlist.sort(key=lambda a: -a["ub_rebate_day"])
    print("\n=== TOP CANDIDATES (UPPER-BOUND rebate; CFTC discount-weighted; ignores adverse selection) ===")
    print(f"{'ticker':<30}{'side':>4}{'px':>6}{'cap$':>6}{'exScore':>8}{'2side':>6}{'ubShr':>7}{'ub$/d':>7}{'$/d pool':>9}{'vol24':>8}")
    for a in shortlist:
        print(f"{a['ticker']:<30}{a['side']:>4}{a['price']:>6.2f}{a['cap_usd']:>6.0f}"
              f"{a['existing_score']:>8.0f}{('yes' if a['two_sided'] else 'NO'):>6}{a['ub_share']:>7.2f}"
              f"{a['ub_rebate_day']:>7.2f}{a['pool_per_day']:>9.1f}{a['volume_24h']:>8.0f}")

    DATA.mkdir(exist_ok=True)
    out = DATA / "lip_candidates.json"
    out.write_text(json.dumps(shortlist, indent=2))
    print(f"\nSaved {len(shortlist)} candidates to {out}")
    print("NOTE: ub$/d is an UPPER BOUND (size-share of pool, no adverse selection). "
          "Phase 1 (book_observe.py) measures the real competition + run-over risk.")


if __name__ == "__main__":
    main()
