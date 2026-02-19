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
   - Key tennis matches (top-seeded players, interesting matchups)
   - All economics markets (Fed rate, GDP, CPI, etc.)
   - Skip markets with extreme prices (below 5% or above 95% in the scan) — but you can't see prices, so skip markets that seem obviously one-sided from the question text alone

5. **Research each market BLIND.** Follow the methodology in `tools/methodology.md`:
   - Use web search to find current evidence (injuries, form, stats, news)
   - Apply anchor-and-adjust: start from base rate, list each factor with +/- adjustment, show the math
   - Sports: 12-step checklist. Economics: 10-step checklist.
   - Output: probability estimate (0.01-0.99), confidence (high/medium/low), key evidence
   - If calibration feedback exists, apply the bias corrections
   - Use parallel research agents for different categories (NBA, soccer, tennis, economics)
   - Target 5 web searches per market

6. **CRITICAL: Do NOT look at prices until ALL estimates are complete.**

7. **Reveal prices and calculate EV.** After all estimates are done, read `data/latest_scan.json` for market prices. For each researched market:
   - For YES direction: `Edge = AI_estimate - market_price`
   - For NO direction: `Edge = market_price - AI_estimate`
   - Pick whichever direction has positive edge
   - `Fee = 0.07 x price x (1 - price)`
   - `EV = Edge - Fee`
   - Kelly fraction: `Edge / (1 - price) x 0.33` for YES, `Edge / price x 0.33` for NO

8. **Filter and rank.** Apply strict bet gating rules (see `tools/methodology.md`):
   - **High confidence**: EV >= 5%
   - **Medium confidence**: EV >= 8%
   - **Low confidence**: NEVER recommend, regardless of EV
   - **Weak estimate (42-58%)**: EV >= 12%, regardless of confidence
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
