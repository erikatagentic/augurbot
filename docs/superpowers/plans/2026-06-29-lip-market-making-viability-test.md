# Plan — Test LIP Market-Making Viability at $130

**Date:** 2026-06-29
**Status:** Approved direction; to be executed in a fresh session
**Goal:** Measure (not estimate) whether Kalshi Liquidity-Incentive-Program (LIP) market-making is net +EV at $130, and produce a go/no-go on funding it up.

---

## Context — why this, why now

A full-day edge investigation proved AugurBot has **no autonomous forecasting / arbitrage / bet-selection edge** at the tradeable price — markets are efficient (see `docs/AUGURBOT-STATE.md` for the 7-row scorecard, all efficient/dead, including a purpose-built ELO model that loses to the closing line). The **only +EV path found** is the Kalshi **LIP**: get *paid a rebate* for posting resting liquidity near best price, independent of predicting outcomes.

Erik is willing to fund this **if it's viable**, but wants to first test whether it can work at the current ~$130 balance before committing more capital. This plan is a **cheap-first, phased test** that measures the real economics.

**Urgency:** the LIP subsidy is currently set to end **~Sept 1, 2026** [help.kalshi.com, verified this session]. The rebate is the half that makes this +EV (vs break-even market-making), so the earning window is ~2 months. Move fast or accept the test may outlast the program.

---

## The core question (one equation)

```
Net EV per day = rebate_earned + spread_captured − adverse_selection_losses − fees
```

In an efficient market, `spread_captured ≈ adverse_selection_losses` (pure market-making nets ~0). **The rebate is the entire edge.** The unknown is whether, at $130 scale, `rebate > adverse_selection`. Measure it on real fills; do not trust the estimate.

---

## Verified vs unknown (carry into the fresh session)

**VERIFIED this session:**
- LIP pays a snapshot-weighted share of resting liquidity **even if unfilled** (random book snapshot ~1×/sec; order must be near best + live the whole second; brief quotes catch ~10%). Pools **$10–$1,000/day per market**. Retail-eligible (excludes Kalshi affiliates / Market-Maker-Agreement holders / IB-FCM). Ends ~Sept 1 2026. [help.kalshi.com]
- Kalshi order placement works (`tools/bet.py` → `kalshi.place_order`); auth is live.
- Risk rails exist and wrap order placement: `backend/services/risk_guard.py` (kill switch, daily-loss, drawdown halt, exposure caps, slippage recheck).
- Maker fee = 25% of taker; `calculator.kalshi_fee(price, maker=True)`.

**VERIFIED this session (gate, 2026-06-29) — the incentive data IS in the API:**
- `GET /trade-api/v2/incentive_programs?status=active&type=liquidity` returns the live list [probed: status 200, 20 active liquidity programs]. Fields per program: `market_ticker`, `period_reward` (total pool for the period, in centi-cents → /10000 = dollars), `target_size_fp` (qualifying resting size), `discount_factor_bps`, `start_date`, `end_date`, `status`. So Phase 0 is **fully autonomous** — no dashboard/browser needed. (My earlier "not in the API" was wrong: I'd tried `/incentives`; the real path is `/incentive_programs`.)
- Live snapshot: pools **$100-$200 per period** (e.g. KXFEAR $200, KXSWIFTWEDDING $100); **`target_size_fp` = 1000 contracts**.
- **Capital math:** 1000 contracts × price = capital to meet the qualifying size. At ~$0.13/contract that's ~$130; at $0.50 it's $500. So $130 CAN meet the qualifying size **only on low-priced (sub-~15¢) incentivized markets** — that's the band Phase 0 must target.

**STILL UNKNOWN — resolve in Phase 0:**
- **Period length** (is `period_reward` per hour / per day?) — determines $/day. Get from the program object's start/end + reward cadence, or the help-center mechanics.
- Exact scoring: how `target_size_fp` + `discount_factor_bps` (distance-from-midpoint discount) combine into your liquidity score / share.
- Live orderbook depth to measure existing qualifying liquidity = our share (try `GET /trade-api/v2/markets/{ticker}/orderbook`).
- How **earned incentives are reported** for Phase 2 measurement (check `status=paid_out` on `/incentive_programs`, or a settlements/statement endpoint).

---

## Phases (each gates the next — stop early if a gate fails)

### Phase 0 — Recon (free, no money, ~1-2 hrs) — `tools/lip_recon.py`
1. Pull the live program list: `GET /trade-api/v2/incentive_programs?status=active&type=liquidity` (authed; already works). Parse `market_ticker`, `period_reward`/10000=$pool, `target_size_fp`, `end_date`.
2. **Filter to the affordable band:** for each program, fetch the market's price; keep those where `target_size_fp × price ≤ $130` (i.e. we can actually fund the qualifying size). On a $200 pool that's the sub-~15¢ markets.
3. Resolve period length (so $pool → $/day) and the scoring formula (`target_size_fp` + `discount_factor_bps`).
4. For each affordable program, fetch live orderbook depth (`GET /markets/{ticker}/orderbook`), compute existing qualifying liquidity, and the THEORETICAL rebate at $130:
   `rebate ≈ our_qualifying_size / (existing_qualifying_liquidity + our_qualifying_size) × pool_per_day`.
5. **GATE:** if best-case theoretical rebate `< ~$1/day` across all affordable programs → **STOP, not viable at $130** (answer: "needs $X capital"). If `≥ a few $/day` → Phase 1.

### Phase 1 — Paper measurement (free, no money, ~3-5 days observation)
1. `tools/book_observe.py`: snapshot the order book of 1-2 candidate markets every ~30-60s; log best bid/ask, qualifying liquidity, and how often/how far best price jumps.
2. Compute (a) paper rebate share at min qualifying size; (b) **adverse-selection proxy**: how often a resting near-best order would have been run over by a fast move (a fill you'd regret).
3. `paper_net = paper_rebate − paper_adverse_selection`.
4. **GATE:** paper_net clearly positive → Phase 2. Near-zero/negative → STOP, document "not viable at $130".

### Phase 2 — Live micro-test (real money, $130, 5-7 days)
1. `tools/lip_make.py`: a resting-order MANAGER — place min-qualifying limit orders near best in 1-2 markets; monitor; cancel/replace to stay near best; **pull on fast moves**; manage inventory back to flat when filled; **`risk_guard` wraps everything** (kill switch + exposure caps).
2. Run 5-7 days. Measure ACTUAL: rebate earned (Kalshi statement/dashboard) + realized fill P&L (incl. adverse selection) + fees = **NET**.
3. **Kill number:** if net `< ~$1-2/day` averaged → STOP, conclude "not viable at $130; needs $X".
4. **DECISION:** net positive AND scaling math works → fund to $2-5k and run for real (before Sept 1). Net negative → LIP not viable at retail scale; bank the lab.

---

## What to build (reuses existing infra)
- `tools/lip_recon.py` — Phase 0: incentivized-market list + theoretical-rebate calc.
- `tools/book_observe.py` — Phase 1: orderbook logger + paper rebate-vs-adverse-selection.
- `tools/lip_make.py` — Phase 2: resting-order manager (reuses `kalshi.place_order`, `risk_guard`, maker fees).
- Reuse: `KalshiClient`, `backend/services/risk_guard.py`, `calculator.kalshi_fee(maker=True)`.

---

## Verification / discipline (Re-Audit + Rule F)
- Phase 0 must **cite the actual dashboard pool sizes + qualifying rules + the orderbook endpoint response**, not estimates.
- Before any live order (Phase 2): confirm `our_share × pool > fees + expected_adverse_selection` using the **real cited book depth** (Rule F: empirical probe before risking money).
- Phase 2 NET must cite the **actual Kalshi rebate statement + the real fill log** (`data/bets.json`), never simulated P&L — every false edge this session died at the gap between simulated and executable.
- Default-deny: first live order is a high-stakes production action — surface the projected economics and get an explicit go before firing (Rule B).

---

## Honest framing to hold onto
This is the only +EV path, but it's a small **liquidity-provision business**, not a winning bettor: the edge is the subsidy + spread, not being right. It's capital-gated (a few $k+ to matter), it's a thin grind against funded quant MMs, and the subsidy expires ~Sept 1. The $130 test exists to answer one thing cheaply: **does the rebate clear adverse selection at all?** If yes, scaling is a capital decision. If no, we have a real answer and we stop.
