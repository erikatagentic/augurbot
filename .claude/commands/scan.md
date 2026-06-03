# Full Market Scan & Research

Run a complete AugurBot scan: fetch markets from Kalshi, research each one blind (no prices), calculate expected value, and present bet recommendations.

## Steps

1. **Read calibration feedback (MANDATORY).** Read `data/calibration_feedback.txt`. You MUST apply these bias corrections to your base rates before starting any research. For example, if it says "Soccer: underestimate by 51%", raise all soccer estimates by that amount. Do not skip this step.

2. **Fetch markets.** Run:
   ```
   backend/.venv/bin/python3 tools/scan.py
   ```
   This saves `data/latest_scan.json` (with prices) and `data/blind_markets.json` (without prices, but with `liquidity_tier`).

   **Timing guidance:** Prefer scanning **2-4 hours before tip-off** for best results. For evening games (7pm+ ET), scan after 3pm ET. For afternoon games, scan after 11am ET. Late-breaking lineup info is the most impactful factor and our negative CLV (-4.2%) shows the market adjusts to info we miss by scanning too early.

3. **Read blind markets.** Read `data/blind_markets.json`. Do NOT read `data/latest_scan.json` yet — you must not see prices during research.

3b. **Check for existing active recommendations.** Read `data/recommendations.json` and collect all tickers where `status` is `"active"`. When researching markets in step 5, SKIP any market whose ticker already exists as an active recommendation. This prevents researching the same game twice across scans.

4. **Screen and select candidates.** From the blind markets, select the best research candidates using this priority order:

   **PRIORITY 1 — Basketball (our edge, research ALL of these):**
   - All NBA game winners (skip spreads and totals unless the line looks interesting)
   - All NCAA Basketball game winners from power conferences (ACC, Big 12, Big Ten, SEC, Big East)
   - Skip small-conference NCAA games where data is thin

   **PRIORITY 2 — Economics (keep when available):**
   - All economics markets (Fed rate, GDP, CPI, unemployment, payrolls)
   - These have excellent data sources (CME FedWatch, GDPNow) and rarely surprise

   **DO NOT RESEARCH:**
   - **ALL soccer (including UCL)** — 44.7% hit rate, draw problem makes binary markets structurally harder. Dropped entirely March 2026.
   - Tennis — 39% hit rate, worst Brier (0.273). Dropped entirely.
   - Any sport where we lack model-based data sources
   - Markets that seem obviously one-sided from the question text alone

5. **Research each market BLIND.** Follow the full methodology in `tools/methodology.md` and reference `tools/data_sources.md` for URLs and Firecrawl schemas:
   - Apply anchor-and-adjust: start from base rate, list each factor with +/- adjustment, show the math
   - Sports: 12-step checklist (including new Step 2b model lookup). Economics: 10-step checklist.
   - Output: probability estimate (0.01-0.99), confidence (high/medium/low), key evidence
   - If calibration feedback exists, apply the bias corrections
   - Target **8-10 information lookups per market** (mix of `firecrawl_scrape`, `firecrawl_search`, and `WebSearch`):

   **REQUIRED lookups per sports market (minimum 8):**
   1. `firecrawl_scrape`: Injury report (structured JSON from ESPN — see data_sources.md for schema)
   2. `firecrawl_scrape`: Team/player stats page (structured JSON from reference site — Basketball Reference, FBref, ATP Tour)
   3. `firecrawl_search`: Win probability model lookup (ESPN BPI, KenPom, ELO model — use as base rate)
   4. `firecrawl_search`: Recent form and results (last 5-10 games/matches)
   5. `firecrawl_search`: Head-to-head history
   6. `WebSearch`: Breaking news and contextual factors
   7. `WebSearch`: Expert analysis and previews (NOT betting odds)
   8. `WebSearch`: Additional context (weather, coaching, travel, schedule)

   **For Economics markets, replace lookups 1-5 with:**
   1. `firecrawl_scrape`: Nowcast data (GDPNow, Cleveland Fed, CME FedWatch — see data_sources.md)
   2. `firecrawl_search`: Consensus forecast
   3. `firecrawl_search`: Leading indicators and recent economic data
   4. `WebSearch`: External shocks, policy changes
   5. `WebSearch`: Expert commentary

5b. **Dispatch parallel research subagents.** For each category of markets, use Task tool to spawn **3 parallel subagents** per market:

   | Agent | Tools | Returns |
   |-------|-------|---------|
   | **Stats Agent** | `firecrawl_scrape` with JSON schemas from data_sources.md | Injuries, W-L record, ratings, efficiency metrics |
   | **Model Agent** | `firecrawl_search` | Model-based win probability (replaces hardcoded base rate) |
   | **News Agent** | `firecrawl_search` + `WebSearch` | Form, H2H, breaking news, context, schedule |

   All three run in parallel per market. After all complete, synthesize findings into the anchor-and-adjust estimate.

   **Example dispatch for an NBA game:**
   - Stats Task: `firecrawl_scrape` ESPN injuries page + Basketball Reference team stats for both teams
   - Model Task: `firecrawl_search` "{Team A} vs {Team B} NBA win probability prediction model 2026"
   - News Task: WebSearch for breaking news, recent form, schedule context

   **Fallback**: If `firecrawl_scrape` fails on a URL, fall back to `firecrawl_search`. If that fails, fall back to `WebSearch`.

6. **CRITICAL: Do NOT look at prices until ALL estimates are complete.**

7. **Reveal prices and score with the shared pipeline (do NOT hand-compute EV).** After all estimates are done, read `data/latest_scan.json`. EV is now computed in code against the price you actually transact, not last/mid — buying YES pays `yes_ask`, buying NO sells at `yes_bid`. Hand math silently used the wrong (mid/last) price and booked edges that vanished at fill.
   - For each researched market, build a row `{ "ticker", "ai_estimate", "yes_ask", "yes_bid", "confidence" }` using `yes_ask` and `yes_bid` straight from `data/latest_scan.json` (NOT `price_yes`/last).
   - Write the array to `/tmp/augur_estimates.json` and run:
     ```
     backend/.venv/bin/python3 tools/score.py /tmp/augur_estimates.json
     ```
   - Use the returned `recommend`, `direction`, `edge`, `ev`, `kelly_fraction` directly. Do not recompute by hand.

8. **Filter and rank.** The gating below is enforced in code by `tools/strategy.py` (single source of truth) — `score.py` already applies all of it, so trust its `recommend` flag. Listed here for transparency:
   - Executable pricing: edge measured against `yes_ask` (YES) / `yes_bid` (NO).
   - **Spread gate**: markets with `yes_ask - yes_bid > 0.10` are skipped as too wide/stale.
   - **MEDIUM/HIGH confidence**: EV >= 10% (0.8x Kelly; HIGH is mapped to MEDIUM).
   - **Low confidence**: never recommend. **Coin-flip estimate (42-58%)**: hard block. **Max divergence (>12% from the executable entry price)**: never recommend.
   - **Adjustment budget check** (this one is YOUR job during research, not in score.py): total adjustments from the model base rate must not exceed +/-15% (or +/-10% from hardcoded). Show the math.
   - Sort recommendations (`recommend: true`) by `ev` descending. It is better to recommend 0 bets than weak ones.
   - NOTE: early backtesting (June 2026) is inconclusive — only ~99 of 359 resolved markets had a recorded bid/ask book (the bot didn't archive the book before March), so the sample is thin and recent-only. On that slice these gates + executable pricing admit very few bets and the small sample was unprofitable. Treat every recommendation as provisional pending threshold re-tuning and more book data.

9. **Present recommendations table** with columns: Market, Ticker, Bet Direction, AI Estimate, Market Price, Edge, EV, Confidence.

10. **Save recommendations.** Read existing `data/recommendations.json` first. For each researched market:
    - If a rec with the same ticker already exists AND status is `"active"`, UPDATE that entry with new values
    - Otherwise, APPEND a new entry

    **CRITICAL:**
    - Copy `ticker` and `sport_type` EXACTLY from `blind_markets.json`. Never construct, abbreviate, or guess.
    - Use ONLY "high", "medium", or "low" for confidence (no "medium-high" etc.)

    ```json
    {
      "scan_time": "ISO timestamp",
      "ticker": "exact ticker from blind_markets.json",
      "question": "Market question text",
      "category": "sports or economics",
      "sport_type": "exact sport_type from blind_markets.json",
      "direction": "yes or no",
      "ai_estimate": 0.XX,
      "market_price": 0.XX,
      "edge": 0.XX,
      "ev": 0.XX,
      "confidence": "high/medium/low",
      "kelly_fraction": 0.XX,
      "reasoning_summary": "1-2 sentence summary of key reasoning",
      "status": "active",
      "outcome": null,
      "resolved_at": null
    }
    ```

11. **Ask user** if they want to place bets on any recommendations.
