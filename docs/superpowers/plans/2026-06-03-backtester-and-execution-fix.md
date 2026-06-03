# Backtester + Execution Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backtester that validates strategy changes against real outcomes, then use it to prove and ship the execution fix (compute EV against the price we actually pay, plus a spread gate).

**Architecture:** A pure-Python `tools/strategy.py` holds the deterministic EV → gate → Kelly → P&L pipeline (reusing `backend/services/calculator.py`, which imports cleanly from `tools/` with `backend` on `sys.path`). `tools/backtest.py` replays historical recommendations through that pipeline with tunable parameters and reports metrics. The same `strategy.py` then backs the live `/scan` math, replacing Claude's hand computation so executable-price EV is enforced in code, not prose.

**Tech Stack:** Python 3 (the repo's `backend/.venv`), pytest (to be installed), stdlib `json`/`statistics`. No new runtime deps.

**Scope note:** This plan covers Workstream 1 (backtester) and Workstream 2 (execution fix) from the spec `docs/superpowers/specs/2026-06-03-augurbot-strategy-upgrade-design.md`. Workstream 3 (model anchor / Step 2b automation) is forward-tested and gets its own plan after this one validates.

---

## File Structure

- Create: `tools/strategy.py` — deterministic EV/gate/Kelly/P&L wrappers + executable-price + spread-gate logic. Shared by backtester and live scan.
- Create: `tools/backtest.py` — replay engine + CLI + report.
- Create: `tests/__init__.py`, `tests/conftest.py` — put `backend/` and repo root on `sys.path`.
- Create: `tests/test_executable_ev.py`, `tests/test_strategy.py`, `tests/test_backtest.py`.
- Modify: `backend/services/calculator.py` — extend `calculate_ev` with optional executable prices (backward compatible).
- Modify: `.claude/commands/scan.md` — steps 7-8 call `tools/strategy.py` instead of hand math; add spread gate.

---

## Task 0: Test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Install pytest into the existing venv**

Run:
```bash
backend/.venv/bin/pip install pytest
```
Expected: "Successfully installed pytest-..." (no other deps disturbed).

- [ ] **Step 2: Create the test package + path shim**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:
```python
"""Put repo root and backend/ on sys.path so tests import tools.* and services.*"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
```

- [ ] **Step 3: Verify pytest collects with the shim**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/ -q
```
Expected: "no tests ran" (exit code 5) — confirms collection works, nothing to run yet.

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: add pytest infra and sys.path shim"
```

---

## Task 1: Executable-price EV in calculator.py

The bug: `calculate_ev` (`backend/services/calculator.py:77,82`) computes both directions against a single `market_price`, which comes from a `last_price → mid → ask` fallback (`backend/services/kalshi.py:15-16`). A YES buy pays the ask; a NO buy sells at the bid. We add optional executable prices, fully backward compatible.

**Files:**
- Modify: `backend/services/calculator.py:56-100`
- Test: `tests/test_executable_ev.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_executable_ev.py`:
```python
from services.calculator import calculate_ev


def test_yes_edge_measured_against_ask_not_mid():
    # AI says 0.60. last/mid = 0.50 (looks like +0.10 edge) but ask = 0.57.
    r = calculate_ev(0.60, 0.50, "kalshi", yes_ask=0.57, yes_bid=0.53)
    assert r is not None
    assert r["direction"] == "yes"
    assert abs(r["edge"] - 0.03) < 1e-6  # 0.60 - 0.57, not 0.60 - 0.50


def test_no_edge_measured_against_bid():
    # AI says 0.40 (YES). Market mid 0.50, bid 0.47, ask 0.53.
    # NO edge = yes_bid - ai_prob = 0.47 - 0.40 = 0.07.
    r = calculate_ev(0.40, 0.50, "kalshi", yes_ask=0.53, yes_bid=0.47)
    assert r is not None
    assert r["direction"] == "no"
    assert abs(r["edge"] - 0.07) < 1e-6


def test_phantom_edge_disappears_against_ask():
    # AI 0.55, mid 0.50 -> looks like +0.05 YES edge, but ask 0.56 kills it.
    r = calculate_ev(0.55, 0.50, "kalshi", yes_ask=0.56, yes_bid=0.44)
    # YES edge negative (0.55-0.56), NO edge negative (0.44-0.55) -> no bet.
    assert r is None


def test_backward_compatible_when_no_executable_prices():
    # Omitting yes_ask/yes_bid must reproduce the old single-price behavior.
    assert calculate_ev(0.60, 0.50, "kalshi") == calculate_ev(
        0.60, 0.50, "kalshi", yes_ask=0.50, yes_bid=0.50
    )
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_executable_ev.py -v
```
Expected: FAIL — `calculate_ev() got an unexpected keyword argument 'yes_ask'`.

- [ ] **Step 3: Implement the extension**

Replace `backend/services/calculator.py` lines 56-100 (`def calculate_ev` through its final `return None`) with:
```python
def calculate_ev(
    ai_probability: float,
    market_price: float,
    platform: str,
    yes_ask: float | None = None,
    yes_bid: float | None = None,
) -> dict | None:
    """Compare the AI estimate to the price actually transacted and return EV.

    Executable pricing: buying YES pays ``yes_ask``; buying NO sells YES at
    ``yes_bid`` (NO entry price ``1 - yes_bid``). When the executable prices
    are omitted, both directions fall back to ``market_price`` — the legacy
    behavior — so existing callers are unaffected.

    Args:
        ai_probability: AI's estimated probability of YES (0.01 – 0.99).
        market_price: Reference YES price (0 – 1); fallback when no book given.
        platform: Platform name for fee lookup.
        yes_ask: Best YES ask (price paid to buy YES). Defaults to market_price.
        yes_bid: Best YES bid (price received selling YES = buying NO).
                 Defaults to market_price.

    Returns:
        Dict with ``direction``, ``edge``, ``ev`` for the better direction, or
        ``None`` if neither direction is profitable after fees.
    """
    yes_price = yes_ask if yes_ask is not None else market_price
    no_anchor = yes_bid if yes_bid is not None else market_price

    # YES direction: pay the ask, fee on the YES entry price
    yes_edge = ai_probability - yes_price
    yes_fee = get_platform_fee(platform, yes_price)
    yes_ev = yes_edge - yes_fee

    # NO direction: sell YES at the bid, fee on the NO entry price (1 - bid)
    no_edge = no_anchor - ai_probability
    no_fee = get_platform_fee(platform, 1.0 - no_anchor)
    no_ev = no_edge - no_fee

    if yes_ev > 0 and yes_ev >= no_ev:
        return {
            "direction": Direction.yes.value,
            "edge": round(yes_edge, 4),
            "ev": round(yes_ev, 4),
        }

    if no_ev > 0:
        return {
            "direction": Direction.no.value,
            "edge": round(no_edge, 4),
            "ev": round(no_ev, 4),
        }

    return None
```

- [ ] **Step 4: Run to verify pass**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_executable_ev.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/calculator.py tests/test_executable_ev.py
git commit -m "feat: EV against executable ask/bid in calculate_ev (backward compatible)"
```

---

## Task 2: Backtester data loading + metric reproduction (sanity anchor)

The sanity anchor is exact reproduction of the canonical metrics in `data/performance.json`: `overall_brier` 0.2111 and `hit_rate` 0.4722, computed over its 360 `resolved_markets` rows. If the replay can reproduce those from `ai_estimate` + `outcome`, the metric math is trustworthy.

**Files:**
- Create: `tools/backtest.py`
- Test: `tests/test_backtest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_backtest.py`:
```python
import json
from pathlib import Path

from tools.backtest import load_resolved, overall_metrics

ROOT = Path(__file__).resolve().parent.parent


def test_reproduces_performance_json_brier_and_hitrate():
    perf = json.loads((ROOT / "data" / "performance.json").read_text())
    rows = load_resolved(ROOT / "data" / "performance.json")
    assert len(rows) == perf["total_resolved"]  # 360
    m = overall_metrics(rows)
    assert abs(m["brier"] - perf["overall_brier"]) < 1e-3   # 0.2111
    assert abs(m["hit_rate"] - perf["hit_rate"]) < 1e-3     # 0.4722


def test_load_resolved_filters_unresolved():
    rows = load_resolved(ROOT / "data" / "performance.json")
    assert all(r.get("outcome") is not None for r in rows)
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_backtest.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.backtest'`.

- [ ] **Step 3: Implement loader + metrics**

Create `tools/backtest.py`:
```python
"""Replay historical recommendations through the strategy pipeline.

Validates SIZING / GATING / SELECTION changes against real outcomes. Does NOT
validate a new forecasting model (no historical model anchors exist).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from services.calculator import calculate_brier_score  # noqa: E402


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
```

- [ ] **Step 4: Run to verify pass**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_backtest.py -v
```
Expected: 2 passed (brier ≈ 0.2111, hit_rate ≈ 0.4722).

- [ ] **Step 5: Commit**

```bash
git add tools/backtest.py tests/test_backtest.py
git commit -m "feat: backtester loader + metric reproduction of performance.json"
```

---

## Task 3: Strategy pipeline module (gate + Kelly + simulated P&L)

`tools/strategy.py` is the single deterministic implementation of the bet decision, shared by the backtester and (Task 6) the live scan. It wraps `calculator.py` and adds the simulated-P&L convention used for backtesting (fixed 1-unit stake per recommended bet, so results are comparable to `performance.json`'s `simulated_pnl_per_contract`).

**Files:**
- Create: `tools/strategy.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strategy.py`:
```python
from tools.strategy import evaluate_market, simulate_pnl_per_contract


def test_evaluate_recommends_clear_edge():
    # Edge must clear EV>=0.10 AND stay within the 0.12 divergence cap. With
    # executable pricing YES edge == (ai - ask), so use a low-priced market to
    # keep the fee small: ai 0.32 vs ask 0.20 -> edge 0.12, fee ~0.011, EV ~0.109.
    d = evaluate_market(
        ai_estimate=0.32, yes_ask=0.20, yes_bid=0.18, confidence="medium"
    )
    assert d["recommend"] is True
    assert d["direction"] == "yes"
    assert d["ev"] >= 0.10


def test_evaluate_rejects_coinflip():
    d = evaluate_market(
        ai_estimate=0.52, yes_ask=0.40, yes_bid=0.38, confidence="medium"
    )
    assert d["recommend"] is False  # 0.42-0.58 hard block


def test_evaluate_rejects_when_ask_eats_edge():
    # mid would show edge, but ask removes it
    d = evaluate_market(
        ai_estimate=0.59, yes_ask=0.585, yes_bid=0.40, confidence="medium"
    )
    assert d["recommend"] is False


def test_simulate_pnl_win_and_loss():
    # YES bought at ask 0.50, resolves YES -> +1.0 profit per contract (1.0-0.50)
    assert simulate_pnl_per_contract("yes", 0.50, outcome=True) == 0.50
    # resolves NO -> lose the 0.50 paid
    assert simulate_pnl_per_contract("yes", 0.50, outcome=False) == -0.50
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_strategy.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.strategy'`.

- [ ] **Step 3: Implement the strategy module**

Create `tools/strategy.py`:
```python
"""Deterministic bet-decision pipeline shared by the backtester and live scan.

Single source of truth for: executable-price EV, the recommendation gate, the
spread gate, Kelly sizing, and per-contract simulated P&L.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from services.calculator import (  # noqa: E402
    calculate_ev,
    calculate_kelly,
    should_recommend,
)
from models.schemas import Confidence  # noqa: E402


def spread_too_wide(yes_ask: float, yes_bid: float, max_spread: float) -> bool:
    """True if the book is too wide/stale to trade."""
    if yes_ask <= 0 or yes_bid <= 0:
        return True
    return (yes_ask - yes_bid) > max_spread


def evaluate_market(
    ai_estimate: float,
    yes_ask: float,
    yes_bid: float,
    confidence: str,
    kelly_fraction: float = 0.20,
    max_bet_fraction: float = 0.03,
    max_spread: float = 0.10,
    platform: str = "kalshi",
) -> dict:
    """Run the full decision for one market against the executable book.

    Returns a dict with ``recommend`` (bool) and, when recommended,
    ``direction``, ``edge``, ``ev``, ``kelly_fraction``.
    """
    mid = (yes_ask + yes_bid) / 2.0
    base = {"recommend": False, "direction": None, "edge": 0.0, "ev": 0.0,
            "kelly_fraction": 0.0}

    if spread_too_wide(yes_ask, yes_bid, max_spread):
        return base

    ev_data = calculate_ev(ai_estimate, mid, platform,
                           yes_ask=yes_ask, yes_bid=yes_bid)
    if ev_data is None:
        return base

    # Divergence/coin-flip gate uses the executable entry price for the side.
    entry = yes_ask if ev_data["direction"] == "yes" else yes_bid
    if not should_recommend(ev_data["ev"], confidence, ai_estimate, entry):
        return base

    kelly = calculate_kelly(
        ev_data["edge"], entry, ev_data["direction"],
        Confidence(confidence), kelly_fraction, max_bet_fraction,
    )
    return {
        "recommend": kelly > 0,
        "direction": ev_data["direction"],
        "edge": ev_data["edge"],
        "ev": ev_data["ev"],
        "kelly_fraction": kelly,
    }


def simulate_pnl_per_contract(direction: str, entry_price: float,
                              outcome: bool) -> float:
    """Profit/loss for one contract entered at ``entry_price`` (YES-equivalent).

    YES: pay entry_price, receive 1.0 if outcome True.
    NO: pay (1 - entry_price), receive 1.0 if outcome False.
    """
    if direction == "yes":
        return round((1.0 - entry_price) if outcome else -entry_price, 4)
    no_cost = 1.0 - entry_price
    return round((1.0 - no_cost) if not outcome else -no_cost, 4)
```

- [ ] **Step 4: Run to verify pass**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_strategy.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/strategy.py tests/test_strategy.py
git commit -m "feat: shared strategy pipeline (executable EV + spread gate + Kelly)"
```

---

## Task 4: Backtester sweep over archived scans (executable-price replay)

Replay archived scans (which carry `yes_bid`/`yes_ask`) joined to resolved outcomes, sweeping parameters. This is where the executable-price fix is proven: re-scoring historical recommendations against the ask shows how many "edges" survive.

**Files:**
- Modify: `tools/backtest.py`
- Test: `tests/test_backtest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backtest.py`:
```python
from tools.backtest import run_sweep


def test_run_sweep_returns_metrics_per_paramset():
    paramsets = [
        {"name": "ask_strict", "max_spread": 0.05, "ev_min_via_gate": True},
        {"name": "ask_loose", "max_spread": 0.20, "ev_min_via_gate": True},
    ]
    results = run_sweep(ROOT / "data", paramsets)
    assert {r["name"] for r in results} == {"ask_strict", "ask_loose"}
    for r in results:
        assert "n_bets" in r and "sim_pnl" in r and "hit_rate" in r
    # A looser spread gate admits at least as many bets as a strict one.
    by = {r["name"]: r for r in results}
    assert by["ask_loose"]["n_bets"] >= by["ask_strict"]["n_bets"]
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_backtest.py::test_run_sweep_returns_metrics_per_paramset -v
```
Expected: FAIL — `cannot import name 'run_sweep'`.

- [ ] **Step 3: Implement the sweep**

Append to `tools/backtest.py`:
```python
import glob

from tools.strategy import evaluate_market, simulate_pnl_per_contract


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
```

- [ ] **Step 4: Run to verify pass**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_backtest.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/backtest.py tests/test_backtest.py
git commit -m "feat: backtester param sweep over archived books with executable pricing"
```

---

## Task 5: Backtester CLI + comparison report

**Files:**
- Modify: `tools/backtest.py`

- [ ] **Step 1: Add CLI entrypoint**

Append to `tools/backtest.py`:
```python
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
    print(f"{'paramset':<16}{'n_bets':>8}{'hit':>8}{'sim_pnl':>10}")
    for r in run_sweep(data_dir, _default_paramsets()):
        print(f"{r['name']:<16}{r['n_bets']:>8}{r['hit_rate']:>8}"
              f"{r['sim_pnl']:>10}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the backtester end to end**

Run:
```bash
backend/.venv/bin/python3 tools/backtest.py
```
Expected: prints the baseline line (Brier 0.2111, hit 0.4722) then a table of paramsets with `n_bets`, `hit`, `sim_pnl`. Record which spread cap maximizes `sim_pnl` — that value feeds Task 6.

- [ ] **Step 3: Commit**

```bash
git add tools/backtest.py
git commit -m "feat: backtester CLI with spread-cap comparison report"
```

---

## Task 6: Wire executable-price EV + spread gate into the live scan

The live `/scan` currently has Claude compute EV by hand against `market_price` (`.claude/commands/scan.md:81-96`). Replace that with a call to `tools/strategy.py` so executable pricing and the spread gate are enforced in code.

**Files:**
- Create: `tools/score.py` — thin CLI: read estimates + revealed book, print recommendation rows.
- Modify: `.claude/commands/scan.md:79-97`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strategy.py`:
```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_score_cli_emits_recommendation(tmp_path):
    payload = [{
        "ticker": "TEST-1", "ai_estimate": 0.70,
        "yes_ask": 0.55, "yes_bid": 0.53, "confidence": "medium",
    }]
    f = tmp_path / "in.json"
    f.write_text(json.dumps(payload))
    out = subprocess.check_output(
        [sys.executable, str(ROOT / "tools" / "score.py"), str(f)],
        text=True,
    )
    rows = json.loads(out)
    assert rows[0]["ticker"] == "TEST-1"
    assert rows[0]["recommend"] is True
    assert rows[0]["direction"] == "yes"
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_strategy.py::test_score_cli_emits_recommendation -v
```
Expected: FAIL — score.py does not exist.

- [ ] **Step 3: Implement score.py**

Create `tools/score.py`:
```python
"""Score researched markets against the revealed book using the shared pipeline.

Input JSON: list of {ticker, ai_estimate, yes_ask, yes_bid, confidence}.
Output JSON (stdout): same rows annotated with recommend/direction/edge/ev/kelly.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.strategy import evaluate_market


def main() -> None:
    rows = json.loads(Path(sys.argv[1]).read_text())
    out = []
    for r in rows:
        d = evaluate_market(
            ai_estimate=r["ai_estimate"],
            yes_ask=r["yes_ask"], yes_bid=r["yes_bid"],
            confidence=r.get("confidence", "medium"),
        )
        out.append({**r, **d})
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify pass**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/test_strategy.py -v
```
Expected: all pass.

- [ ] **Step 5: Update the scan command**

In `.claude/commands/scan.md`, replace steps 7-8 (lines 79-97) so the EV step reads `yes_bid`/`yes_ask` from `data/latest_scan.json`, builds the input JSON, and runs:
```
backend/.venv/bin/python3 tools/score.py /tmp/augur_estimates.json
```
Use the returned `recommend`/`direction`/`edge`/`ev`/`kelly_fraction` directly instead of hand math. Document the spread gate (default 0.10, or the value found in Task 5) and that EV is now measured against the ask (YES) / bid (NO). Keep the blind rule: prices are still revealed only after estimates.

- [ ] **Step 6: Commit**

```bash
git add tools/score.py .claude/commands/scan.md tests/test_strategy.py
git commit -m "feat: live scan scores via shared executable-price pipeline (no hand math)"
```

---

## Final verification

- [ ] **Run the full suite**

Run:
```bash
backend/.venv/bin/python3 -m pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Run the backtester and record the winning spread cap**

Run:
```bash
backend/.venv/bin/python3 tools/backtest.py
```
Capture the table in the cycle notes. Success criterion (spec WS2): a paramset with clearly positive `sim_pnl` net of executable pricing. If none is positive, that itself is the finding — surface it to Erik before live use; do not ship a knowingly negative-EV config.

- [ ] **Push**

```bash
git push
```

---

## Decision Log
- Sanity anchor changed from "reproduce -$61.47/+$9.77" to "reproduce Brier 0.2111 + hit 0.4722 from performance.json's 360 resolved rows" — because -$61.47 is actual fills (bets.json), not a backtester output, and the +$9.77 per-contract figure depends on an unstated sizing convention. Brier/hit are deterministic from ai_estimate+outcome. — verified this session.
- EV math centralized in `tools/strategy.py` (shared by backtester + live scan) rather than left as Claude hand-math — because hand math can't be tested and silently used the wrong (mid/last) price. — calculator.py:77 + scan.md:81-96.
- Backtester joins resolved outcomes to archived-scan books by ticker, keeping the tightest book per ticker — because a ticker can appear in several archived scans with different spreads.
- WS3 (model anchor) deferred to its own plan — forward-tested, no historical anchors to backtest against.
- Sweep varies `max_spread` only; the EV threshold (0.10) and divergence cap (0.12) stay hardcoded in `should_recommend` for now. FAST-FOLLOW once Task 5 prints baselines: executable pricing makes YES edge == divergence, so the 0.12 cap + 0.10 EV gate squeeze the qualifying band to roughly edge ∈ [0.11, 0.12] — very few bets may clear. If Task 5 shows too few bets or negative `sim_pnl`, parametrize those two thresholds into `evaluate_market`/`should_recommend` and add them to the sweep before any live use. Surface the baseline table to Erik first.
