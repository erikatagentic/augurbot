# AugurBot — Full Cycle

Run the complete AugurBot workflow: check results, check balance, scan markets, research blind, calculate EV, and place bets.

## Steps

### Phase 1: Check Results

1. **Check for resolved markets.** Run:
   ```
   backend/.venv/bin/python3 tools/results.py
   ```
   This checks all open bets and active recommendations against Kalshi, updates `data/performance.json`, and generates `data/calibration_feedback.txt`.

2. **Show results** to the user — any new W/L outcomes, P&L, and overall stats (Brier score, hit rate).

### Phase 2: Check Balance

3. **Check Kalshi balance.** Run:
   ```
   backend/.venv/bin/python3 tools/balance.py
   ```
   Note the cash balance for bet sizing later. Show the user their balance, positions, and any resting orders.

### Phase 3: Scan & Research

4. **Check for calibration feedback.** If `data/calibration_feedback.txt` exists, read it. Use this during research to correct known biases.

5. **Fetch markets.** Run:
   ```
   backend/.venv/bin/python3 tools/scan.py
   ```

6. **Read blind markets.** Read `data/blind_markets.json`. Do NOT read `data/latest_scan.json` yet — you must not see prices during research.

6b. **Check for existing active recommendations.** Read `data/recommendations.json` and collect all tickers where `status` is `"active"`. When researching markets in step 8, SKIP any market whose ticker already exists as an active recommendation.

7. **Screen and select candidates.** From the blind markets, select the best research candidates:
   - All NBA/NCAA game winners (skip spreads and totals unless interesting)
   - Top soccer matches (Champions League, La Liga, Serie A, Premier League)
   - Key tennis matches — **Be selective**: only top-30 players or interesting matchups. Skip obscure lower-ranked matches.
   - All economics markets (Fed rate, GDP, CPI, etc.)
   - Skip markets that seem obviously one-sided from the question text alone

8. **Research each market BLIND.** Follow the full methodology in `tools/methodology.md` and reference `tools/data_sources.md` for URLs and Firecrawl schemas:
   - Apply anchor-and-adjust: start from base rate, list each factor with +/- adjustment, show the math
   - Sports: 12-step checklist (including Step 2b model lookup). Economics: 10-step checklist.
   - Output: probability estimate (0.01-0.99), confidence (high/medium/low), key evidence
   - If calibration feedback exists, apply the bias corrections
   - Target **8-10 information lookups per market** (mix of `firecrawl_scrape`, `firecrawl_search`, and `WebSearch`):

   **REQUIRED lookups per sports market (minimum 8):**
   1. `firecrawl_scrape`: Injury report (structured JSON from ESPN — see data_sources.md)
   2. `firecrawl_scrape`: Team/player stats (structured JSON from reference site)
   3. `firecrawl_search`: Win probability model lookup (ESPN BPI, KenPom, ELO — use as base rate)
   4. `firecrawl_search`: Recent form and results (last 5-10 games/matches)
   5. `firecrawl_search`: Head-to-head history
   6. `WebSearch`: Breaking news and contextual factors
   7. `WebSearch`: Expert analysis and previews (NOT betting odds)
   8. `WebSearch`: Additional context (weather, coaching, travel, schedule)

   **For Economics markets, replace lookups 1-5 with:**
   1. `firecrawl_scrape`: Nowcast data (GDPNow, Cleveland Fed, CME FedWatch)
   2. `firecrawl_search`: Consensus forecast
   3. `firecrawl_search`: Leading indicators and recent data
   4. `WebSearch`: External shocks, policy changes
   5. `WebSearch`: Expert commentary

   **Dispatch 3 parallel subagents per category** via Task tool:
   - **Stats Agent**: `firecrawl_scrape` for injuries + stats (JSON schemas from data_sources.md)
   - **Model Agent**: `firecrawl_search` for win probability models (base rate replacement)
   - **News Agent**: `firecrawl_search` + `WebSearch` for form, H2H, news, context

   All three run in parallel. Synthesize findings into anchor-and-adjust estimate after all complete.

9. **CRITICAL: Do NOT look at prices until ALL estimates are complete.**

10. **Reveal prices and calculate EV.** After all estimates are done, read `data/latest_scan.json` for market prices. For each researched market:
    - For YES direction: `Edge = AI_estimate - market_price`
    - For NO direction: `Edge = market_price - AI_estimate`
    - Pick whichever direction has positive edge
    - `Fee = 0.07 x price x (1 - price)`
    - `EV = Edge - Fee`
    - Kelly fraction: `Edge / (1 - price) x 0.33` for YES, `Edge / price x 0.33` for NO

11. **Filter and rank.** Apply strict bet gating rules (see `tools/methodology.md`):
    - **High confidence**: EV >= 5%
    - **Medium confidence**: EV >= 8%
    - **Low confidence**: NEVER recommend, regardless of EV
    - **Weak estimate (42-58%)**: EV >= 12%, regardless of confidence
    - **ADDITIONAL GATING**: Do NOT assign HIGH confidence unless BOTH: (a) a model-based win probability was found, and (b) structured injury data confirms key players' status. If either is missing, cap at MEDIUM.
    - Sort by EV descending. Better to recommend 0 bets than weak ones.

12. **Present recommendations table** with columns: Market, Ticker, Bet Direction, AI Estimate, Market Price, Edge, EV, Confidence.

13. **Save recommendations.** Read existing `data/recommendations.json` first. For each researched market:
    - If a rec with the same ticker already exists AND status is `"active"`, UPDATE that entry with new values
    - Otherwise, APPEND a new entry
    - Copy `ticker` and `sport_type` EXACTLY from `blind_markets.json`. Use ONLY "high", "medium", or "low" for confidence.
    ```json
    {
      "scan_time": "ISO timestamp",
      "ticker": "exact ticker from blind_markets.json",
      "question": "Market question text",
      "category": "sports or economics",
      "sport_type": "NBA, Soccer, Tennis, etc.",
      "direction": "yes or no",
      "ai_estimate": 0.00,
      "market_price": 0.00,
      "edge": 0.00,
      "ev": 0.00,
      "confidence": "high/medium/low",
      "kelly_fraction": 0.00,
      "reasoning_summary": "1-2 sentence summary of key reasoning",
      "status": "active",
      "outcome": null,
      "resolved_at": null
    }
    ```

### Phase 4: Place Bets

14. If no recommendations with EV >= 3%, tell the user "No +EV bets found this scan" and stop.

15. **Calculate bet sizes.** For each of the top 5 bets by EV:
    - Max per bet = 5% of cash balance (from step 3)
    - For YES bets: contracts = floor(max_per_bet / (yes_price / 100))
    - For NO bets: contracts = floor(max_per_bet / ((100 - yes_price) / 100))
    - Minimum 1 contract per bet

16. **Show confirmation table** before placing any bets:
    | # | Market | Direction | Contracts | Price | Cost | Potential Profit |

    Show total cost across all bets.

17. **Place each bet** using:
    ```
    backend/.venv/bin/python3 tools/bet.py TICKER SIDE COUNT PRICE
    ```
    Where PRICE is the YES price in cents (from latest_scan.json, field `price_yes` x 100).

18. **Save placed bets.** Append each placed bet to `data/bets.json`:
    ```json
    {
      "placed_at": "ISO timestamp",
      "ticker": "KXMARKET-TICKER",
      "question": "Market question",
      "direction": "yes or no",
      "contracts": 10,
      "yes_price": 51,
      "cost": 4.90,
      "order_id": "from bet.py output",
      "order_status": "resting or executed",
      "status": "open",
      "pnl": null,
      "closed_at": null
    }
    ```

19. **Show final summary**: results from resolved bets, new bets placed, total risk, remaining balance.
