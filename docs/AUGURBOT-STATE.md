# AugurBot — State of the System (2026-06-29)

> Canonical "where things stand" doc. Written after a full-day edge investigation.
> Chronological detail is in `docs/superpowers/plans/2026-06-29-risk-rails-and-arbitrage.md`.

## One-line verdict

The liquid prediction markets a small bot can reach are **efficient**. No forecasting edge survives the market's own accuracy plus execution costs at a $130 bankroll with seconds-to-minutes (Claude-loop) latency. The durable value built is the **risk infrastructure and the evaluation machine**, not a live trading edge.

## Edge scorecard (all tested with live data this session)

| Edge | How tested | Verdict | Key evidence |
|------|-----------|---------|--------------|
| Out-forecast the market (blind prediction) | Brier over 359 resolved markets | **Efficient — we tie it** | our Brier 0.2108 vs market 0.2117 |
| Cross-venue arb, taker | Live CLOB books, correct fees | **Breakeven** | venues price identically; the earlier "−2c dead" was a 100× Polymarket fee bug |
| Cross-venue arb, maker | Live CLOB books | Thin (~1-2c) market-making | = half the spread; vs MMs Polymarket pays to post |
| NCAA Basketball forecasting | Brier by category + split-half | **Dead** | real Brier edge (0.2106 vs 0.2349, n=127) but decays in-sample (+0.036→+0.013), and 50/127 exceed the 12% divergence gate → ~2 tradeable bets/season |
| Weather, mean | NWS forecast vs market, 5 cities | **Efficient** | market = NWS within ~1°F; the "72% edge" was a single-model (gfs025) artifact |
| Weather, distribution/tails | 488-sample calibration backtest | **Efficient** | tail buckets priced 0.026 won 0.029; buying cheap tails = +0.0007/contract before spread |

## The operative reason live trading lost money

Verified from `data/bets.json`: of 89 orders, **48 were resting limit orders and 100% expired unfilled** (`resting_never_filled`, $0). The entire **−$61.47** realized loss came from the **41 taker fills at a 34.1% win rate**. So "use limit orders to capture the spread" is not an untested idea — it ran in production and got **zero fills**. On these books a resting order either misses or fills only when adversely selected.

## Why no autonomous bet-selection rule works (the favorite-betting fallacy)

A natural idea: "bet the favorites, rack up dozens of small winning trades." Tested on 492 real
settled Kalshi markets at the morning (pre-outcome) price: betting every favorite priced ≥0.70 won
**70% of trades but netted −$1.05 after fees** (−$1.15 buying at the ask); ≥0.80 won 75%, netted
−$0.55. A high win rate is a feeling, not a profit — a favorite at 85¢ pays 15¢ to win and costs 85¢
to lose, so one loss erases ~6 wins, and on a fair market the EV is ≈ −fee per contract.

The market is correctly priced (calibration: every price band wins at its price, 488 samples), so
*selecting* which fair-priced bets to take cannot beat it — favorites, underdogs, "high-EV," all the
same fair coin. And trading at VOLUME makes it worse, not safer: more trades converge you to your true
EV, which is negative after costs (exactly the bot's history: many trades → −$61.47, profit factor
0.59). Volume reveals an edge, it doesn't create one.

An autonomous bot profits on prediction markets in only two ways, both tested: (1) a real information
edge (ours ties the market — none), or (2) getting paid outside the bet (LIP subsidy — capital-gated
market-making, below).

## The only un-killed money path (and its ceiling)

**Kalshi Liquidity Incentive Program** (help.kalshi.com, through ~Sept 1 2026): pays a snapshot-weighted share of resting liquidity **even if unfilled** — the one mechanism that decouples reward from adverse selection. Retail-eligible. Reward = (your share of qualifying liquidity) × pool ($10–$1,000/day per market).
- **Ceiling at $130:** a few dollars/day, only in markets thin enough that your size is a meaningful fraction; the public market API does **not** expose which markets are incentivized (no field), so you'd work from Kalshi's incentives dashboard.
- **It scales with capital, not edge.** At $2-5k+ you could rank in more/bigger pools, but you're then competing with "small scrappy teams making six figures" running automation.

## What was built (the durable value)

- `backend/services/risk_guard.py` — deterministic pre-trade gate on the manual bet path: kill switch (STOP file), daily-loss limit, drawdown halt, position + exposure caps, pre-fire slippage/liquidity recheck. Sizes off live balance.
- `backend/services/analytics.py` — failure classification (bad_estimate / news_timing / external_shock) + Sharpe / profit factor / max drawdown.
- `backend/services/arb_matcher.py` + `arb_detector.py` — structured same-event matcher + **correct maker/taker-aware** cross-venue arb engine; `PolymarketClient.fetch_order_book` (live CLOB).
- `tools/arb_scan.py` — paper-mode cross-venue scanner (taker vs maker edge per pair).
- Corrected fee model (`calculator.py`): `kalshi_fee`/`polymarket_fee` are price-proportional + maker/taker aware (the bug that faked a dead-arb conclusion).
- 64 tests green. A disciplined paper lab that disproved 6 edge theses for ~$0.

## The decision

1. **Stop live trading; keep the lab + rails (recommended).** No real-money edge at $130. The evaluation machine is the asset — point it at the next idea instead of grinding.
2. **Fund up ($2-5k+) and run a liquidity-provision grind via the LIP.** A real but thin business against pros; only if prediction-market income is a genuine goal. Free next step: read the LIP incentives dashboard to size the real ceiling before funding.

## Process lessons (cost real money / saved real money this session)

- **Too-good-to-be-true numbers are artifacts.** The "−2c arb" was a 100× fee bug; the "72% weather edge" was a single-model bias. Investigate, don't believe.
- **Don't call dead prematurely either.** Three "it's dead" calls got pushed back; one was a real bug. The honest answer required testing each to ground.
- **Backtest before believing, against executable prices and settled outcomes** — midpoints and simulated fills both flatter the edge (sim +9.77 vs actual −61.47).
