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
   - Key tennis matches (top-seeded players, interesting matchups)
   - All economics markets (Fed rate, GDP, CPI, etc.)
   - Skip markets that seem obviously one-sided from the question text alone

8. **Research each market BLIND.** Follow the methodology in `tools/methodology.md`:
   - Use web search to find current evidence (injuries, form, stats, news)
   - Apply anchor-and-adjust: start from base rate, list each factor with +/- adjustment, show the math
   - Sports: 12-step checklist. Economics: 10-step checklist.
   - Output: probability estimate (0.01-0.99), confidence (high/medium/low), key evidence
   - If calibration feedback exists, apply the bias corrections
   - Use parallel research agents for different categories (NBA, soccer, tennis, economics)
   - Target 5 web searches per market

9. **CRITICAL: Do NOT look at prices until ALL estimates are complete.**

10. **Reveal prices and calculate EV.** After all estimates are done, read `data/latest_scan.json` for market prices. For each researched market:
    - For YES direction: `Edge = AI_estimate - market_price`
    - For NO direction: `Edge = market_price - AI_estimate`
    - Pick whichever direction has positive edge
    - `Fee = 0.07 x price x (1 - price)`
    - `EV = Edge - Fee`
    - Kelly fraction: `Edge / (1 - price) x 0.33` for YES, `Edge / price x 0.33` for NO

11. **Filter and rank.** Only recommend bets with EV >= 3% (0.03). Sort by EV descending.

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
