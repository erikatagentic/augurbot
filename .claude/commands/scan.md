# Full Market Scan & Research

Run a complete AugurBot scan: fetch markets from Kalshi, research each one blind (no prices), calculate expected value, and present bet recommendations.

## Steps

1. **Read calibration feedback (MANDATORY).** Read `data/calibration_feedback.txt`. You MUST apply these bias corrections to your base rates before starting any research. For example, if it says "Soccer: underestimate by 51%", raise all soccer estimates by that amount. Do not skip this step.

2. **Fetch markets.** Run:
   ```
   backend/.venv/bin/python3 tools/scan.py
   ```
   This saves `data/latest_scan.json` (with prices) and `data/blind_markets.json` (without prices).

3. **Read blind markets.** Read `data/blind_markets.json`. Do NOT read `data/latest_scan.json` yet — you must not see prices during research.

3b. **Check for existing active recommendations.** Read `data/recommendations.json` and collect all tickers where `status` is `"active"`. When researching markets in step 5, SKIP any market whose ticker already exists as an active recommendation. This prevents researching the same game twice across scans.

4. **Screen and select candidates.** From the blind markets, select the best research candidates:
   - All NBA/NCAA game winners (skip spreads and totals unless interesting)
   - Top soccer matches (Champions League, La Liga, Serie A, Premier League)
   - Key tennis matches — **Be selective**: only research matches involving top-30 players or interesting matchups. Skip obscure lower-ranked matches where data is thin.
   - All economics markets (Fed rate, GDP, CPI, etc.)
   - Skip markets that seem obviously one-sided from the question text alone

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

7. **Reveal prices and calculate EV.** After all estimates are done, read `data/latest_scan.json` for market prices. For each researched market:
   - For YES direction: `Edge = AI_estimate - market_price`
   - For NO direction: `Edge = market_price - AI_estimate`
   - Pick whichever direction has positive edge
   - `Fee = 0.07 x price x (1 - price)`
   - `EV = Edge - Fee`
   - Kelly fraction: `Edge / (1 - price) x 0.33` for YES, `Edge / price x 0.33` for NO

8. **Filter and rank.** Apply strict bet gating rules (see `tools/methodology.md`):
   - **High confidence**: EV >= 8%
   - **Medium confidence**: EV >= 8%
   - **Low confidence**: NEVER recommend, regardless of EV
   - **Weak estimate (42-58%)**: EV >= 12%, regardless of confidence
   - **ADDITIONAL GATING**: Do NOT assign HIGH confidence unless BOTH:
     (a) A model-based win probability was found (not just hardcoded base rate)
     (b) Structured injury data confirms key players' status
     If either is missing, cap confidence at MEDIUM regardless of narrative strength.
   - Sort remaining recommendations by EV descending.
   - It is better to recommend 0 bets than to recommend weak ones.

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
