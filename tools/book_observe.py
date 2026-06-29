#!/usr/bin/env python3
"""LIP Phase 1 — passive orderbook observation.

Snapshots candidate markets' orderbooks on an interval and logs, per snapshot:
best bid/ask on the side we'd provide, mid, spread, in-band qualifying depth,
and our hypothetical size-share of the pool. Between snapshots it tracks how far
the mid moves — the proxy for adverse selection (how often a near-best resting
order would get run over).

This measures the two things Phase 0's arithmetic could NOT: the REAL competing
liquidity, and the run-over risk. It does NOT place orders and risks no money.
Net P&L is provisional here; the real net comes from Phase 2 live fills.

Append-only: re-run across days to accumulate into the same JSONL.

Usage:
    # validate (short burst)
    backend/.venv/bin/python3 tools/book_observe.py --minutes 3 --interval 30
    # accumulate
    backend/.venv/bin/python3 tools/book_observe.py --minutes 60 --interval 45
    # summarize accumulated data only
    backend/.venv/bin/python3 tools/book_observe.py --summarize
"""
import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from lip import fetch_orderbook, load_client, our_share, qualifying_score

DATA = Path(__file__).resolve().parent.parent / "data"
LOG = DATA / "lip_observations.jsonl"
CANDS = DATA / "lip_candidates.json"


def snapshot(client, cand: dict) -> dict | None:
    ob = fetch_orderbook(client, cand["ticker"])
    if ob is None:
        return None
    side = cand["side"]
    disc = cand.get("discount_factor", 0.5)
    target = cand["target_size"]
    our_levels = ob[side]  # resting bids on our side, best first
    other = ob["no" if side == "yes" else "yes"]
    if not our_levels:
        return None
    best = our_levels[0][0]
    best_other = other[0][0] if other else None
    # For a YES side, the complementary NO best implies the YES ask = 1 - no_best.
    implied_ask = (1 - best_other) if best_other is not None else None
    mid = (best + implied_ask) / 2 if implied_ask is not None else best
    spread = (implied_ask - best) if implied_ask is not None else None
    # CFTC discount-weighted score; we post `target` at best (N=0 -> our score = target).
    existing_score, _, _ = qualifying_score(our_levels, target, disc)
    _, other_reached, _ = qualifying_score(other, target, disc)
    two_sided = bool(other_reached)  # snapshot scores only if BOTH sides reach target
    share = our_share(existing_score, target) if two_sided else 0.0
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ticker": cand["ticker"], "side": side,
        "best": round(best, 4), "implied_ask": round(implied_ask, 4) if implied_ask is not None else None,
        "mid": round(mid, 4), "spread": round(spread, 4) if spread is not None else None,
        "existing_score": round(existing_score, 1), "two_sided": two_sided,
        "paper_share": round(share, 4),
        "pool_per_day": cand["pool_per_day"],
        "paper_rebate_day": round(share * cand["pool_per_day"], 3),
    }


def summarize(out_path: Path) -> None:
    if not out_path.exists():
        print("No observations logged yet.")
        return
    rows = [json.loads(l) for l in out_path.read_text().splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r["ticker"]].append(r)
    print(f"\n=== OBSERVATION SUMMARY ({len(rows)} snapshots, {len(by)} markets) ===")
    print(f"{'ticker':<30}{'snaps':>6}{'2side%':>7}{'avgShr':>7}{'avgReb/d':>9}{'midMove':>8}{'sweeps':>7}{'span(min)':>10}")
    for tk, rs in sorted(by.items()):
        rs.sort(key=lambda r: r["ts"])
        shares = [r["paper_share"] for r in rs]
        rebs = [r["paper_rebate_day"] for r in rs]
        twos = [1 for r in rs if r.get("two_sided")]
        mids = [r["mid"] for r in rs]
        moves = [abs(mids[i] - mids[i - 1]) for i in range(1, len(mids))]
        sweeps = sum(1 for m in moves if m >= 0.02)  # >=2c mid jump = likely run-over
        avg_move = (sum(moves) / len(moves)) if moves else 0.0
        t0 = datetime.fromisoformat(rs[0]["ts"]); t1 = datetime.fromisoformat(rs[-1]["ts"])
        span = (t1 - t0).total_seconds() / 60
        print(f"{tk:<30}{len(rs):>6}{100*len(twos)/len(rs):>6.0f}%{sum(shares)/len(shares):>7.2f}"
              f"{sum(rebs)/len(rebs):>9.2f}{avg_move*100:>7.2f}c{sweeps:>7}{span:>10.1f}")
    print("\n2side% = snapshots where BOTH sides reach Target Size (others pay $0 to everyone).")
    print("midMove = avg |mid change|/snapshot; sweeps = # of >=2c mid jumps (adverse-selection proxy).")
    print("avgReb/d is an UPPER BOUND: no adverse selection, and per-side score normalization")
    print("may halve realized payout. $1.00/period minimum applies (below that you earn $0).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=20.0)
    ap.add_argument("--interval", type=float, default=45.0, help="Seconds between snapshots")
    ap.add_argument("--tickers", type=str, default=None, help="Comma-separated; else use data/lip_candidates.json")
    ap.add_argument("--n", type=int, default=4, help="How many top candidates to observe")
    ap.add_argument("--summarize", action="store_true", help="Only summarize the existing log")
    args = ap.parse_args()

    if args.summarize:
        summarize(LOG)
        return

    client = load_client()
    if args.tickers:
        wanted = set(args.tickers.split(","))
        cands = [c for c in json.loads(CANDS.read_text()) if c["ticker"] in wanted]
    else:
        cands = json.loads(CANDS.read_text())[:args.n]
    if not cands:
        print("No candidates. Run tools/lip_recon.py first."); return

    print(f"Observing {len(cands)} markets every {args.interval:.0f}s for {args.minutes:.0f} min:")
    for c in cands:
        print(f"  {c['ticker']} ({c['side']} @ {c['price']}, pool ${c['pool_per_day']}/day, ub_share {c.get('ub_share')})")

    DATA.mkdir(exist_ok=True)
    deadline = time.time() + args.minutes * 60
    n_snaps = 0
    with LOG.open("a") as f:
        while time.time() < deadline:
            for c in cands:
                rec = snapshot(client, c)
                if rec:
                    f.write(json.dumps(rec) + "\n"); f.flush(); n_snaps += 1
            if time.time() < deadline:
                time.sleep(args.interval)
    print(f"\nLogged {n_snaps} snapshots to {LOG}")
    summarize(LOG)


if __name__ == "__main__":
    main()
