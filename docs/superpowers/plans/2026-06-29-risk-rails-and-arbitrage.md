# Plan — Risk Rails + Cross-Venue Arbitrage

**Date:** 2026-06-29
**Status:** Approved direction (awaiting build go)
**Decisions locked:** Build BOTH workstreams. polymarket.us is KYC'd + funded → arb path can reach live.

---

## Context — Why This Change

Erik pasted Anthropic's "build a prediction-market trading bot with Claude Skills" guide and asked for a plan to implement it. The honest finding from exploring this repo: **AugurBot already implements ~80% of that guide** — scan with volume/liquidity/time filters [tools/scan.py:138, 260-271], blind research by Claude [backend/services/researcher.py:93-99], EV + fractional-Kelly sizing [backend/services/calculator.py:115-162, 236-289], calibration feedback, and full performance tracking [tools/results.py].

More important: the guide's core promise — "estimate probability better than the market and you profit" — **was already tested here and failed.** A June 2026 backtest swept EV-threshold and divergence-cap across the backtestable slice and found **no configuration is +EV** (brain commit 9fd88e7, tagged `no-edge` / `efficient-market`). Real performance: **-$61.47 P&L, 47% hit rate, 0.211 Brier across 360 resolved markets** [data/performance.json]. The guide's "68.4% win rate / 2.14 Sharpe" is Anthropic's marketing backtest, not what blind estimation delivered on Kalshi.

So "implement the guide" does NOT mean rebuild the prediction pipeline more elaborately. It means take the two genuinely-additive things the guide has that this repo lacks:

1. **Operational risk + learning rails** (guide Steps 4-5) — edge-agnostic, ship now, and a prerequisite for any safe live trading.
2. **Cross-venue arbitrage** — the one direction this repo's own roadmap already named as the only real edge ("the genuinely-edge-producing ones are all arbitrage/Polymarket tools" [tools/roadmap.md:102-103]). The Polymarket client is already built [backend/services/polymarket.py], just unwired.

**Intended outcome:** (A) AugurBot can't blow up its account and learns from losses structurally; (B) AugurBot trades a structural cross-venue edge that does NOT depend on out-predicting the market.

---

## Live Probe (Rule F) — Arbitrage Surface, Measured

Ran a read-only overlap probe this session (`scratchpad/arb_probe.py`):

- 600 Polymarket markets (vol ≥ $5k) × 267 Kalshi sports+econ markets (vol ≥ $5k).
- **14 candidate same-event pairs** (≥2 shared significant tokens); **~6-8 genuinely the same contract** (Wimbledon ATP/WTA match-winners both venues price: Borges vs Boyer, Navone vs Cobolli, Andreescu vs Zhang, etc.).
- ~50% of naive candidates were FALSE (single-match market colliding with a tournament-outright market).
- Big-volume non-overlap: Polymarket's top markets are World Cup outrights + US politics (2028 nominations, "Trump out as President"); Kalshi's are UFC/tennis. The bot's sports+econ filter misses the politics/crypto/macro markets where overlap would be richest.

**Design consequences (load-bearing):**
- **Arb resurrects dropped categories.** Tennis was dropped for *prediction* (39% hit). Arb trades the price gap on the identical contract, so forecasting skill is irrelevant — and tennis H2H is the cleanest overlap today.
- **Structured matching required.** Fuzzy token overlap is insufficient. Match on parsed participant pair + date + same resolution semantics.
- **Surface is thin today; widening Kalshi categories grows it.** Politics/crypto/macro = optional WS-B extension.
- **Rule F is a standing gate, not a one-off:** every arb run must re-cite the live confirmed-pair count; a near-zero count is a stop.

---

## Explicitly NOT Doing (and why)

- **Multi-model ensemble (Grok/GPT/Gemini/DeepSeek)** — breaks the no-API-cost design, and the backtest says the problem is market efficiency, not single-model noise. Roadmap ranks it LOW [roadmap.md:82-87].
- **Twitter/Reddit sentiment scraping** — adds noise + cost for a thesis already falsified here.
- **SKILL.md repackaging** — cosmetic; the slash-command structure works.
- **Limit orders as default** — directly contradicts the 60%-unfilled lesson [.claude/commands/bet.md:3-4]. Stay on market orders.

---

## Workstream A — Operational Risk + Learning Rails (ship now, edge-agnostic)

Guide's good point: *put risk validation in deterministic Python, not in markdown the model re-interprets.* Centralize it.

**New module: `backend/services/risk_guard.py`** — single entry `pre_trade_check(bet, live_balance, open_bets, recent_pnl) -> (allowed: bool, reasons: list[str])`. Called by `tools/bet.py` before EVERY order (manual path currently skips all of this [risk agent: scanner.py:376-398 covers auto-trade only]). Reuse existing config fractions [config.py:27, 52-53].

| # | Check | What | Reuse / Files |
|---|-------|------|---------------|
| A1 | **Kill switch** | If a `STOP` file exists at repo root, refuse all orders. | new in risk_guard.py; bet.py calls it |
| A2 | **Fix stale bankroll** | Size off LIVE Kalshi balance, not `config.bankroll=10000` [config.py:30] (real ~$162). All % caps are meaningless until this is fixed. | balance.py / kalshi.fetch_balance |
| A3 | **Daily loss limit** | Block new orders if today's realized P&L < -15% of balance. | bets.json `pnl` + balance |
| A4 | **Max drawdown halt** | Block if peak-to-trough drawdown > 8%. | data/bankroll_history.json |
| A5 | **Max concurrent positions** | Block if open bets ≥ 10 (guide says 15; scaled to ~$150 bankroll). | bets.json open count |
| A6 | **Exposure caps on manual path** | Port `max_exposure_fraction` (0.25) + `max_event_exposure_fraction` (0.10) into bet.py. | config.py:52-53; logic mirrors scanner.py:376-398 |
| A7 | **Pre-fire slippage + liquidity recheck** | Re-fetch live bid/ask at order time; abort if spread > 10¢ or executable price moved > 3-5% from the price the EV was computed at. Addresses the stale-price gotcha [MEMORY.md]. | kalshi.py live book; strategy.py:20-24 spread gate |

**Compound / learning (guide Step 5):**

| # | Item | What | Files |
|---|------|------|-------|
| A8 | **Structured failure log** | After each loss in results.py, classify: `bad_estimate` (large \|est−outcome\|, calm CLV) / `news_timing` (CLV moved hard against post-entry) / `execution` (filled far from intent) / `external_shock`. Append to `data/failure_log.jsonl`. | tools/results.py:567-652; CLV already computed [results.py:328-330] |
| A9 | **Close the feedback loop in code** | scan.md feedback is human-applied only [perf agent]. Programmatically inject the calibration summary + recent failure_log into the blind-research context so it can't be silently skipped. | scan.py writes a `data/research_context.txt`; scan.md reads it |
| A10 | **Risk metrics** | Add Sharpe, profit factor, max drawdown to performance.json (guide Step 5 metrics; currently absent [perf agent]). | tools/results.py aggregation |

**WS-A verification:** unit tests in `tests/test_risk_guard.py` — STOP file present → blocked; daily loss exceeded → blocked; exposure over cap → blocked; slippage over tol → blocked; all-clear → allowed. Manual: `touch STOP && backend/.venv/bin/python3 tools/bet.py --dry-run TICKER yes 5 50` → must refuse. Run existing `pytest`.

---

## Workstream B — Cross-Venue Arbitrage (Kalshi ↔ Polymarket), paper → live

Prediction-free edge: same contract, two venues, price gap > combined fees → lock profit.

**B1 — Widen discovery.** Add Polymarket to the scan path. Reuse `PolymarketClient.fetch_markets` (built, public, works [polymarket.py:30-102]). Optional toggle to widen Kalshi categories beyond sports+econ for arb (politics/crypto/macro) — grows the surface per the probe.

**B2 — `backend/services/arb_matcher.py` (the hard part, Rule F-gated).** Structured same-event matcher: parse "A vs B" participant pairs + resolution date; match only markets with identical resolution semantics (match-winner ↔ match-winner, NOT match-winner ↔ tournament-outright). Emit pairs with a confidence score; require manual confirmation on first sighting (probe proved false positives are real). Persist confirmed pairs to `data/arb_pairs.json` so the mapping accrues. Must print live confirmed-pair count every run.

**B3 — `backend/services/arb_detector.py`.** For each confirmed pair, fetch executable prices on BOTH venues (Kalshi yes_ask/yes_bid via KalshiClient; Polymarket via CLOB book/midpoint [polymarket.py:104-148]). True arb when `1 − p_cheap_yes − p_dear_no − fees_both > threshold`, using BOTH fee schedules: Kalshi `0.07·p·(1−p)` [calculator.py] + Polymarket `polymarket_fee=0.02` [config.py:70]. Rank by net edge.

**B4 — Paper mode: `tools/arb_scan.py`.** Output detected opportunities + paper ledger `data/arb_paper.jsonl`. NO live orders. Re-fetch both books at "fill" time (same slippage discipline as A7) to confirm the spread is real and executable, not stale.

**B5 — Live execution (gated): `tools/arb_trade.py`.** Places BOTH legs — Kalshi via existing `kalshi.place_order`, Polymarket via a NEW `PolymarketClient.place_order` using the L2 API creds saved to backend/.env this session. Handle **leg risk** (one fills, the other doesn't → naked position): fill the thinner-liquidity leg first with a marketable limit, then sweep the other; if leg 2 fails, immediately unwind leg 1. The WS-A risk_guard (kill switch, caps) wraps this too. Start at $5-10/leg.

**WS-B verification:** run `tools/arb_scan.py` (paper) → must re-derive the ~6-8 genuine tennis pairs + report any live spread; eyeball matched pairs for false positives; hand-check fee-net math on one example; re-cite the Rule F pair count. Live: one $5/leg round-trip on a confirmed pair, verify both legs filled and net P&L matches the detector's projection within fees.

---

## Sequencing

1. **WS-A first** (A1, A2, A6, A7 are the safety-critical core; A8-A10 follow). Independent, ships now, prerequisite for safe live arb.
2. **WS-B paper** (B1-B4) in parallel — read-only, no dependency.
3. **WS-B live** (B5) only after WS-A risk_guard is in place AND the Polymarket auth scheme is confirmed (see Open Questions).

---

## Open Questions (resolve before WS-B5 live)

1. **Polymarket auth scheme.** Saved creds (Key ID UUID + base64 Secret) look like CLOB **L2** creds, which normally also need a **passphrase**. polymarket.us (US-regulated) uses **Ed25519** keys instead [roadmap.md:107]. Which does your funded account use, and is there a passphrase? B5 can't place orders without the right scheme.
2. **Arb category scope.** Keep arb to current sports+econ overlap (clean, thin), or widen Kalshi scan to politics/crypto/macro to grow the surface (more pairs, more matcher complexity)?

---

## Decision Log

- 2026-06-29 — Build BOTH workstreams; polymarket.us KYC'd+funded (Erik, AskUserQuestion). Arb path planned to live.
- 2026-06-29 — Rejected guide's ensemble / sentiment-scraping / SKILL.md / limit-orders — conflict with no-API-cost design and the 60%-unfilled + efficient-market lessons.
- 2026-06-29 — Probe: ~6-8 genuine same-event pairs today, tennis-concentrated. Arb is prediction-free so dropped categories (tennis) are back in play. Structured matcher required over fuzzy overlap.
- 2026-06-29 — Polymarket API creds saved to backend/.env (gitignored); passphrase/Ed25519 scheme unresolved.

### Execution decisions (WS-A + WS-B paper, shipped 2026-06-29)

- **WS-A risk_guard shipped** (services/risk_guard.py, wired into bet.py, 18 tests). Kill switch / daily-loss / drawdown / position-cap / exposure / slippage all on the manual path. Sizes off LIVE balance.
- **Stale bankroll confirmed real**: config.bankroll=$10k vs live ~$130. Guard uses live balance; config default left as-is (only used by dead auto-trade path).
- **Drawdown halt is ALL-TIME, currently firing at 34.4%** (peak $198.93 → $130.56). With the 8% default this blocks every new manual bet until the account recovers or Erik raises the threshold. Left firing by design (it's a losing strategy) — Erik to choose threshold / trailing-window. OPEN: arb (WS-B) bets are true-locked profit and arguably should bypass the prediction-strategy drawdown halt.
- **Kalshi API schema drift fixed**: live market quotes are `yes_bid_dollars`/`yes_ask_dollars` (string dollars), not `yes_bid`/`yes_ask` cents. bet.py converts. Without this the slippage check silently always-blocked.
- **Polymarket creds are config fields now** (pydantic-settings defaults to extra=forbid; bare .env keys broke config load).
- **WS-B paper shipped** (arb_matcher.py, arb_detector.py, tools/arb_scan.py, 12 tests). Structured H2H matcher + fee-net detector + paper ledger.
- **Date window relaxed 3→14 days, graded confidence**: cross-venue dates encode different things (Kalshi match-date vs Poly resolution-deadline vs Kalshi tournament-close). Participant-pair + full-match-type is the strong signal; date is corroboration only. At ±3 days the matcher returned 0; the real surface is 10 pairs.
- **Live Rule F count (2026-06-29): 10 confirmed same-event pairs** (5 tennis matches × 2 sides), 1 deduped candidate (~2.9c edge off midpoints). Tennis-concentrated, as the probe predicted.
- **Paper edges are off Gamma MIDPOINTS, not the CLOB book** — candidates to verify against both order books before any live fire, NOT confirmed locked profit. B5 (live execution) still gated on the auth-scheme answer.
- **Mirror legs deduped by Poly conditionId** so one match isn't double-logged.

### CRITICAL FINDING — executable arb (2026-06-29, second run)

- Added `PolymarketClient.fetch_order_book()` (public CLOB /book) and wired EXECUTABLE re-pricing into tools/arb_scan.py (best-ask on both legs, not midpoints).
- **Result: all 12 tennis H2H candidates go NEGATIVE at executable book prices.** Midpoint edges were illusory — Poly tennis books are wide (e.g. Vandewinkel midpoint subj 0.76 vs book ask 0.84; Claire Liu +0.045 midpoint → −0.039 exec). Every pair's executable edge < 0 net of fees.
- **Conclusion: cross-venue arb on illiquid tennis R128 markets does NOT survive real spreads.** Same efficient-market / adverse-selection wall as the prediction strategy. Do NOT fund live tennis arb (B5) — it loses.
- The only place arb could survive is HIGH-LIQUIDITY cross-listed events (politics/crypto/macro) where both venues' books are tight. BUT those are Yes/No event markets, not "A vs B" H2H, so the current participant-pair matcher can't match them — that needs a NEW Yes/No semantic/threshold matcher (bigger build, unproven, Rule-F risk of 0 matches). Open: probe whether liquid same-event overlap with a surviving gap even exists before building it.

### CONCLUSIVE — liquid-arb thesis is also DEAD (2026-06-29, time-boxed probe)

- Per "Both" decision, ran the time-boxed liquid-arb probe BEFORE building the Yes/No matcher (Rule F: probe before build).
- Best case for arb = BTC year-end thresholds: tight books on both venues (Kalshi KXBTCMAXY 1c spreads), identical underlying, SAME touch-by-date semantics ("above $X by Dec 31" == "reach $X by Dec 31").
- Aligned 3 thresholds and re-priced against the LIVE Polymarket CLOB book via the production detector:
  - $150k: Kalshi 0.03/0.04 vs Poly book 0.04/0.96 → exec edge −0.023
  - $120k: Kalshi 0.08/0.09 vs Poly book 0.07/0.94 → exec edge −0.015
  - $140k: Kalshi 0.03/0.04 vs Poly book 0.05/0.96 → exec edge −0.019
- **All negative. The venues price BTC thresholds nearly identically.** Cross-venue arb does NOT survive on liquid markets either.
- **DECISION: do NOT build the Yes/No semantic matcher or extend the Kalshi crypto/politics fetch.** The time-boxed probe killed the thesis and saved the build. Arb is dead across illiquid (tennis) AND liquid (crypto).

### Where this leaves AugurBot (honest summary)

Three strategies tested, all -EV after real execution costs: blind prediction (85% of losses are estimate misses, profit factor 0.59 on real fills), tennis H2H arb (negative at executable spreads), liquid crypto arb (negative on tight books). No tradeable edge found anywhere. AugurBot's proven value is now as a DISCIPLINED PAPER LAB that disproves edges for ~$0 before risking capital, with hard risk rails so it can't blow up if a future edge IS found. WS-B5 (live arb execution) is shelved — there's nothing +EV to execute. The Polymarket auth question is moot unless a real edge surfaces.

### CORRECTION (2026-06-29, /gate + /audit) — the "arb dead" conclusion rested on a FEE BUG

- `polymarket_fee = 0.02` [config.py:81] is used as a FLAT 2c/contract absolute in arb_detector.py, while the docstring says "0.02 for 2%" [calculator.py:45]. The REAL Polymarket US fee is ~0.30% taker / 0 maker (with a 0.20% maker rebate) [WebSearch 2026]. So the arb leg fee was ~100x too high.
- Recomputed BTC thresholds live with correct fees: OLD(2c) all −1.5 to −2.3c → TAKER(real) roughly breakeven (−0.6c to +0.5c) → MAKER best-case all POSITIVE (+1.0 to +2.9c).
- **REVISED VERDICT: taker arb is breakeven (efficient market); MAKER (resting limit orders, ~0 fees) shows a thin snapshot edge.** That is MARKET-MAKING, not riskless arb — real fill / adverse-selection / competition risk (Polymarket PAYS makers 100% of taker fees to post tight). NOT free money, but NOT disproven either.
- Also a real DECISION baked in by mistake: we tested TAKER execution (inheriting the prediction strategy's "market orders only / 60% of limit orders expired" lesson), which is the wrong model for arb. Market-making lives on resting limit orders.
- NEXT (gated on Erik): (1) fix the fee model in arb_detector.py (price-proportional, maker/taker aware), (2) confirm exact Polymarket US fee from docs.polymarket.us, (3) re-run scanner maker-aware, (4) tiny ($1-2) live maker-fill test to measure real fill rate + adverse selection. Only after a failed fill test is arb truly dead.

### SHIPPED — fee fix (audit action #1) + a NEW data-found edge (2026-06-29)

- **Fee model fixed (committed):** calculator.py now has `kalshi_fee(price, maker)` + `polymarket_fee(price, maker)` (poly taker 0.30%·price via `polymarket_taker_fee_rate=0.003`, maker 0; kalshi maker = 25% of taker). `detect_arb` rewritten to take full bid+ask per leg + `mode='taker'|'maker'`. arb_scan.py shows TAKER vs MAKER per pair from live books. 64 tests green.
- **Live maker-aware run (14 pairs):** TAKER edge −0.5..−2.4c (cross-spread loses), MAKER edge +0.7..+1.9c (≈half the bid/ask spread captured by posting). Maker edge is thin market-making (fill + adverse-selection + leg risk), not riskless arb.
- **NEW EDGE FOUND in existing data (Erik asked "what other edges?"):**
  - Overall we're TIED with the market on forecasting: our Brier 0.2108 vs market 0.2117 over 359 markets. So no BROAD prediction edge — but we're NOT worse forecasters than the market. Earlier "the model is the problem" was overstated.
  - **NCAA Basketball is a real pocket of forecasting edge:** our Brier 0.2106 vs market 0.2349 (n=127). NBA/Tennis/Soccer we don't beat the market. NCAA sim P&L +6.52/contract (127); on ≥5%-divergence bets +7.03 (n=90, avg +7.8c).
  - The portfolio killer is EXECUTION, not forecasting: sim +9.77 vs actual −61.47 (paying the spread + market-order adverse selection).
- **PROMISING THESIS (the "make it work" path):** specialize in NCAA Basketball (provable forecasting edge) + MAKER execution (stop paying the spread). Two edges stacking. Not proven — gated on whether the +7c NCAA sim edge survives realistic maker-fill execution.
- **NEXT decisive test (gated on Erik):** backtest NCAA ≥5%-divergence bets with maker-style entry (fill at bid-or-better, maker fees) vs the actual market-order fills, using tools/backtest.py. If the edge survives, that's the bot's niche.
- Other untested edge noted: intra-venue Dutch-book / threshold-ladder structural arb (riskless when found, scannable, no cross-venue/latency).

### Guide repos examined + WEATHER edge probed (2026-06-29) — Erik: "true edge, not past performance"

REPOS (read the actual code/READMEs, not the guide's blurbs — guide OVERSOLD them):
- ryanfrigo/kalshi-ai-trading-bot: NOT a 5-model ensemble (single model; multi-agent is unwired scaffolding). README admits "examples lose money", "more trades without edge = faster to zero". Its live-trading lesson: "category discipline mattered more than AI confidence" + maker/NO-side limit orders → INDEPENDENTLY CONFIRMS our NCAA-specialize + maker-execution thesis.
- CarlosIbCu/...-btc-arbitrage-bot: detection-only, ZERO fee/cost accounting ("risk-free if <$1"). The exact trap. Confirms naive arb is fake.
- terauss Rust arb: 404 (gone). pmxt → github.com/pmxt-dev/pmxt is REAL + useful ("CCXT for prediction markets", unified API with real LIMIT-ORDER execution across Kalshi/Polymarket/+12). Good infra if we build.
- suislanchez/...-weather-bot: the credible structural-edge thesis. Open-Meteo 31-member ensemble → bucket probability → trade vs market. BUT "$1.8k profit" is PAPER/simulated, unproven.

GUIDE's real edge thesis (Step 2): "the edge wasn't smarter predictions, it was faster information processing at scale" — i.e. SPEED, or BETTER INFO on a niche the market prices loosely (weather).

WEATHER PROBE (live, this session): pulled Open-Meteo gfs025 ensemble vs live Kalshi KXHIGH buckets (NYC/CHI/MIA/LAX/DEN, Jun 30). Showed HUGE apparent edges (+72% NYC>90, +86% MIA 89-90, +43% LA). **These are CALIBRATION ARTIFACTS, not edge** — the tell: errors point OPPOSITE directions across cities (model 3°F hot in NYC, 4°F cold in Miami). Cause: approximate coords (not Kalshi's exact NWS settlement station) + single grid-cell model (gfs025 ±3-5°F off station) vs a market priced off the correct station. Did NOT believe the number (lesson learned from the fee bug — too-good = artifact).

VERDICT: weather is the best TRUE structural-edge candidate (real authoritative data vs thin niche), but the naive test is a trap. Legitimate path: get Kalshi's exact settlement station per city, pull a bias-corrected/multi-model ensemble (or NWS official probabilistic forecast), and BACKTEST predicted-bucket vs settled-high over 30+ days to measure the REAL (probably small) edge before risking $1. NEXT decisive test gated on Erik: build that calibrated weather backtest.
