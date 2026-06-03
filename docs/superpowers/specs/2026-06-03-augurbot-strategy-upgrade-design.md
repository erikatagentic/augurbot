# AugurBot Strategy Upgrade — Design Spec

**Date:** 2026-06-03
**Status:** Awaiting review
**Scope:** Make the basketball strategy measurably positive before going live on a second venue. Polymarket / both-platform trading is explicitly phase 2 (separate spec).

---

## Problem (verified, not assumed)

The strategy is paper-positive but real-negative. Evidence from this session's analysis of `data/performance.json` and `data/bets.json`:

- Live basketball (NBA + NCAA), 259 resolved markets: simulated P&L **+$12.96**, Brier **0.20**, hit rate **~48%**. NBA Brier 0.191 beats a coin-flip (0.25), so estimates carry signal.
- Actual P&L: **-$61.47** across 89 bets. Of those, **48 expired unfilled (54%)**; of the 41 that filled, only **14 won (34%)** versus the ~48% paper hit rate.
- Dropped sports (Tennis/Soccer/UFC) were 101 of 360 resolved markets with negative simulated edge. Already cut.

**Diagnosis:** forecasting is roughly break-even; the money was lost to execution and the absence of any validation loop. Two confirmed execution leaks:

1. **Limit-order adverse selection** (already mitigated: market orders are the default, `tools/bet.py:96`).
2. **EV computed against a price we never pay.** `calculate_ev` uses `market_price` (`backend/services/calculator.py:77`), which is `price_yes` from a fallback chain of `last_price → mid → ask` (`backend/services/kalshi.py:15-16`). A YES buy pays the **ask**. So booked edges partly evaporate at fill, worse on thin markets where `last_price` is stale.

A third, structural problem: **no backtester and no clean post-overhaul data**, so we cannot currently say whether the current params are +EV. We are flying blind on every strategy change.

---

## Decisions (with rationale)

### Decision Log
- **Model role = anchor, Claude adjusts (not ensemble, not replace).** The methodology already specifies this exact flow: Step 2b "Look up model-based win probability (REPLACES hardcoded base rate)" → "USE IT as your base rate" → adjust within ±15% (`tools/methodology.md:41,45,108`). Option A completes a half-built design instead of rebuilding it. It is also the most reversible: if the anchor hurts, fall back to hardcoded base rates exactly as today. — *because forecasting is not the leak, so minimize disruption to it; and we have no backtester yet to justify the complexity of an ensemble.*
- **Model source = FETCH published calibrated probs, do NOT train our own.** Barttorvik (NCAA) and ESPN BPI/ELO (NBA) are already documented (`tools/data_sources.md:81-110`) and the methodology calls them "already calibrated, use directly" (`tools/methodology.md:158`). — *because a trained model has a low ceiling against an efficient market plus ongoing retraining cost; published numbers are professional calibrated models, free, and methodology-aligned.*
- **EV against executable price.** Compute edge against ask (YES) / 1−bid (NO), not last/mid. — *confirmed flaw at calculator.py:77 + kalshi.py:15-16; likely a large share of the paper-vs-real gap.*
- **Backtester validates sizing/gating/selection only; model anchor is forward-tested.** — *no historical model anchors exist for past games, so the model cannot be replayed.*
- **Build order: backtester → execution fix → model anchor.** — *the backtester is the measurement tool that de-risks the other two and runs on existing data today.*

---

## Workstream 1 — Backtester (`tools/backtest.py`)

**Purpose:** Replay the EV → gating → Kelly-sizing pipeline with configurable parameters against real outcomes, so every future change is validated before risking money.

**Inputs (verified present):**
- `data/recommendations.json` — 385 resolved markets, keys include `ai_estimate`, `market_price`, `outcome`, `edge`, `ev`, `kelly_fraction`, `confidence`, `sport_type`, `direction`.
- `data/scans/*.json` — 29 archived full scans carrying `yes_bid` / `yes_ask` for spread analysis.

**Parameters it sweeps:** EV threshold, Kelly fraction, max-divergence cap, confidence gates, max-spread, and the executable-price toggle (mid vs ask).

**Outputs:** per param set → hit rate, Brier, simulated P&L, number of bets, max drawdown. Side-by-side comparison of param sets.

**Verification / success criteria:**
- Sanity check: replaying *current* params on the full resolved set reproduces the known **-$61.47 actual** and **+$9.77 simulated** figures within rounding. If it cannot reproduce them, the replay logic is wrong and must be fixed before trusting any sweep.
- Replaying current params on the *clean basketball-only* subset answers "is the current strategy +EV?" with a number.

**Reuses:** `backend/services/calculator.py` (already exchange-agnostic) for EV/Kelly so the backtest math matches production exactly.

---

## Workstream 2 — Execution fix

**Change A — EV against executable price.** When computing EV for a candidate bet, use the ask for YES (`yes_ask`) and 1−bid for NO, not `last_price`/mid. Only edges that survive the price we actually pay get recommended.

**Change B — Max-spread gate.** Skip markets where `(yes_ask − yes_bid)` exceeds a threshold (thin/stale market). The spread is already computed at `tools/scan.py:245-247`; this wires it into gating.

**Verification / success criteria:**
- Backtest Change A on the archived scans: recompute historical EV against ask and report how many recommended bets still clear the EV threshold. Expect a meaningful drop (that drop is the phantom edge we were paying for).
- Sweep the spread threshold in the backtester to the value that maximizes simulated P&L net of fees and ask-pricing.
- Combined target: a backtested parameter set on the basketball-only subset with **clearly positive** simulated P&L net of paying the ask + Kalshi fees.

---

## Workstream 3 — Model anchor (automate Step 2b)

**Change:** A fetcher that, for each day's basketball games in the scan, pulls the published calibrated win probability and writes it into `data/blind_markets.json` as the Step 2b anchor, so Claude's research starts from a consistent calibrated number instead of an ad-hoc manual search.

- **NCAA:** Barttorvik (`https://barttorvik.com/`, free, scrapeable — `tools/data_sources.md:90`). KenPom is paywalled; Barttorvik is the documented accessible substitute.
- **NBA:** ESPN BPI game matchup or an ELO-derived probability (`tools/data_sources.md:81-83`).
- Claude still does blind research and adjusts within the existing budget (±15% from a model anchor, tightening toward ±5% if the anchor proves well-calibrated — `tools/methodology.md:108,158`).

**Blind-rule compliance:** these are probability *models*, not betting markets. `tools/data_sources.md:83` already states using them "does NOT violate blind estimation." Confirmed in-policy.

**Verification / success criteria (forward-tested, not backtestable):**
- After N live cycles, compare anchored-estimate Brier against the historical blind NBA Brier (0.191). Success = anchored Brier ≤ blind Brier and bias (`performance.json` `bias_by_category`) shrinks toward zero.
- Guard: if Claude's adjustments on top of the anchor *worsen* Brier vs the raw anchor, tighten the adjustment cap toward ±5%.

**Honest risk:** a pre-game basketball anchor bumps against an efficient market; it may not beat Claude's current 0.191. The forward test exists to catch that before we trust it. The architecture (anchor + adjust) degrades gracefully to today's behavior if the anchor underperforms.

---

## Out of scope (phase 2, separate spec)
- Polymarket read-only data integration.
- Polymarket trading via the US SDK (`Polymarket/polymarket-us-python`).
- Cross-exchange arbitrage and copy-trading.

These wait until this spec's strategy is backtested-positive and forward-confirmed.

---

## Success criteria for the whole upgrade
1. A backtester that reproduces known figures and can score any param set. (WS1)
2. A backtested basketball-only parameter set with clearly positive simulated P&L net of ask-pricing + fees. (WS2)
3. A consistent, automated Step 2b anchor whose forward-tested Brier is ≤ the current blind baseline. (WS3)
