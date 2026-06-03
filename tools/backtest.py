"""Replay historical recommendations through the strategy pipeline.

Validates SIZING / GATING / SELECTION changes against real outcomes. Does NOT
validate a new forecasting model (no historical model anchors exist).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from services.calculator import calculate_brier_score  # noqa: E402

import glob

from tools.strategy import evaluate_market, simulate_pnl_per_contract


def load_resolved(path) -> list[dict]:
    """Load resolved markets from performance.json (resolved_markets) or a
    recommendations.json list. Returns rows with a non-null ``outcome``."""
    data = json.loads(Path(path).read_text())
    rows = data["resolved_markets"] if isinstance(data, dict) else data
    return [r for r in rows if r.get("outcome") is not None]


def overall_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0, "brier": 0.0, "hit_rate": 0.0}
    brier = sum(
        calculate_brier_score(r["ai_estimate"], bool(r["outcome"])) for r in rows
    ) / n
    hits = sum(1 for r in rows if r.get("correct")) / n
    return {"n": n, "brier": round(brier, 4), "hit_rate": round(hits, 4)}


def _outcome_index(perf_path) -> dict:
    """Map ticker -> outcome(bool) from performance.json resolved_markets."""
    rows = load_resolved(perf_path)
    return {r["ticker"]: bool(r["outcome"]) for r in rows}


def _iter_scan_markets(scans_dir):
    """Yield (ticker, yes_bid, yes_ask) for every market in archived scans."""
    for fp in sorted(glob.glob(str(Path(scans_dir) / "scans" / "*.json"))):
        data = json.loads(Path(fp).read_text())
        markets = data.get("markets", data) if isinstance(data, dict) else data
        for m in markets:
            tkr = m.get("platform_id") or m.get("ticker")
            ask, bid = m.get("yes_ask", 0), m.get("yes_bid", 0)
            if tkr and ask and bid:
                yield tkr, bid, ask


def run_sweep(data_dir, paramsets: list[dict]) -> list[dict]:
    """For each paramset, replay resolved markets against archived books.

    Uses each resolved market's recorded ``ai_estimate``/``confidence`` (the
    forecast is held fixed; only sizing/gating/selection vary).
    """
    data_dir = Path(data_dir)
    outcomes = _outcome_index(data_dir / "performance.json")
    resolved = {r["ticker"]: r for r in load_resolved(data_dir / "performance.json")}

    # Best (tightest) book seen per ticker across archived scans.
    books: dict[str, tuple[float, float]] = {}
    for tkr, bid, ask in _iter_scan_markets(data_dir):
        if tkr in resolved:
            prev = books.get(tkr)
            if prev is None or (ask - bid) < (prev[1] - prev[0]):
                books[tkr] = (bid, ask)

    results = []
    for ps in paramsets:
        n_bets = wins = 0
        sim_pnl = 0.0
        for tkr, (bid, ask) in books.items():
            row = resolved[tkr]
            d = evaluate_market(
                ai_estimate=row["ai_estimate"],
                yes_ask=ask, yes_bid=bid,
                confidence=row.get("confidence") or "medium",
                max_spread=ps.get("max_spread", 0.10),
            )
            if not d["recommend"]:
                continue
            n_bets += 1
            entry = ask if d["direction"] == "yes" else bid
            pnl = simulate_pnl_per_contract(d["direction"], entry,
                                            outcomes[tkr])
            sim_pnl += pnl
            if pnl > 0:
                wins += 1
        results.append({
            "name": ps["name"],
            "n_bets": n_bets,
            "wins": wins,
            "hit_rate": round(wins / n_bets, 4) if n_bets else 0.0,
            "sim_pnl": round(sim_pnl, 2),
        })
    return results


def _default_paramsets() -> list[dict]:
    return [
        {"name": "spread<=0.03", "max_spread": 0.03},
        {"name": "spread<=0.05", "max_spread": 0.05},
        {"name": "spread<=0.10", "max_spread": 0.10},
        {"name": "spread<=0.20", "max_spread": 0.20},
    ]


def main() -> None:
    data_dir = ROOT / "data"
    base = overall_metrics(load_resolved(data_dir / "performance.json"))
    print(f"Baseline (all resolved): n={base['n']} "
          f"Brier={base['brier']} hit={base['hit_rate']}")
    print("Actual P&L baseline to beat: -$61.47 (bets.json fills)\n")
    resolved = {r["ticker"] for r in load_resolved(data_dir / "performance.json")}
    scan_tickers = {t for t, _, _ in _iter_scan_markets(data_dir)}
    backtestable = len(resolved & scan_tickers)
    print(f"COVERAGE: only {backtestable} of {len(resolved)} resolved markets "
          f"have a recorded bid/ask book (only 5 of 29 archived scans recorded "
          f"one). The sweep below is a thin, recent-only subsample — NOT a "
          f"representative verdict on the strategy.\n")
    print(f"{'paramset':<16}{'n_bets':>8}{'hit':>8}{'sim_pnl':>10}")
    for r in run_sweep(data_dir, _default_paramsets()):
        print(f"{r['name']:<16}{r['n_bets']:>8}{r['hit_rate']:>8}"
              f"{r['sim_pnl']:>10}")


if __name__ == "__main__":
    main()
