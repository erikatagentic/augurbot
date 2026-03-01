# AugurBot Research Methodology

> This file tells Claude Code how to research prediction markets.
> Follow this methodology exactly when analyzing markets from `data/blind_markets.json`.
> Reference `tools/data_sources.md` for exact URLs, Firecrawl JSON schemas, and search query templates.

---

## Critical Rule

**NEVER look at market prices during research.** Read only `data/blind_markets.json` (which has no prices). The AI must estimate probabilities independently. Prices are revealed only AFTER all estimates are complete, during the EV calculation step.

---

## Workflow

1. **Read** `data/blind_markets.json` — contains questions, categories, dates (NO prices)
2. **Read** `tools/data_sources.md` for URLs and Firecrawl schemas to use during research
3. **Research** each market using `firecrawl_scrape`, `firecrawl_search`, and `WebSearch` (8-10 lookups per market), following the category-specific checklist below
4. **Output** a probability estimate (0.01–0.99) for each market
5. **After ALL estimates**, read `data/latest_scan.json` to get prices and calculate EV

---

## Sports Markets (12-Step Checklist)

Use anchor-and-adjust: start from a base rate, apply adjustments, show the math.

### Step 1: Identify the market
- Sport (NBA, NFL, MLB, NHL, NCAA, Soccer, UFC, etc.)
- Bet type (winner, spread, over/under, prop)
- Look up the base rate below

### Step 2: Injury & roster status (CRITICAL — search first)
- Use `firecrawl_scrape` with JSON schema on the ESPN injuries page for the sport (see `tools/data_sources.md` for URLs and schemas). If scrape fails, fall back to `firecrawl_search` with the injury query template.
- Cross-reference with a second source (CBS Sports, official team social media, beat reporters).
- MUST get injury data for BOTH teams/players before proceeding.
- **If the game is within 4 hours:** Search for "game-day status" or "starting lineup" rather than just "injury report". Pregame warmup reports are more current than injury lists. Players listed as "questionable" may have been upgraded or downgraded.
- Star OUT: -8 to -15% | Role player OUT: -2 to -5% | Questionable: -3 to -7%

### Step 2b: Look up model-based win probability (REPLACES hardcoded base rate)
- Use `firecrawl_search` to find a prediction model estimate for this specific matchup.
- Query: `"{Team A}" vs "{Team B}" win probability prediction model [sport] 2026 -odds -betting`
- Key sources: ESPN BPI, KenPom/Barttorvik (college), Tennis Abstract ELO (tennis), FBref xG models (soccer)
- If a model-based probability is found: **USE IT as your base rate** instead of the hardcoded fallback table below.
- If no model is found: fall back to the hardcoded base rates.
- These are probability MODELS, not betting markets. Using them does NOT violate blind estimation.
- For Soccer: ALWAYS estimate the draw probability separately. P(Team wins) + P(Draw) + P(Opponent wins) = 100%.

### Step 3: Recent form (last 5-10 games)
- Use `firecrawl_scrape` on the team/player's reference page (Basketball Reference, FBref, ATP Tour — see `tools/data_sources.md`) with JSON schema to get structured W-L, ratings, and streaks.
- Supplement with `WebSearch` for very recent changes (last 1-2 games).
- Win/loss streaks, scoring trends, margin of victory
- Strong form vs struggling opponent: +3 to +8%

### Step 4: Head-to-head history
- Last 2-3 years of matchups. Need 5+ games for reliability.
- Strong H2H dominance (5+ games): +2 to +5%
- Fewer than 5 games: cap adjustment at +/-1% only (see Bet Gating Rules)

### Step 5: Home/away advantage
- Already in base rate. Only adjust if team has extreme splits.

### Step 6: Schedule & rest
- Back-to-back with travel: -4 to -6% | Extra rest day: +1 to +3%

### Step 7: Statistical analysis
- Use `firecrawl_scrape` with JSON schema on the relevant reference site to extract: offensive/defensive ratings, net rating, and sport-specific advanced metrics. See `tools/data_sources.md` for exact URLs and schemas per sport.
- Offensive/defensive efficiency, net rating, ATS record

### Step 8: Situational factors
- Playoff implications, rivalry, letdown/look-ahead spots
- "Must-win" motivation: worth 1-2% MAX

### Step 8b: NBA Tanking Detection (February–April, MANDATORY)
From late February through the end of the NBA regular season, tanking is a major factor. Teams out of playoff contention intentionally lose to improve draft lottery odds.

**How to detect a tanking team:**
1. Record well below .500 (under 25 wins by All-Star break)
2. Eliminated from or virtually out of playoff race
3. Star players getting "rest" days, minutes restrictions, or shut down
4. Heavy rotation of G-League callups and young players
5. Recent trades shipping out veterans for picks/prospects

**Current known tankers (2025-26):** Brooklyn (15-39), Washington (15-39), Dallas (19-35), Charlotte (~26-30)

**Adjustments:**
- **NEVER bet ON a tanking team to win**, even at very low prices. Their motivation deficit makes them worse than their stats suggest. A 9¢ YES on a tanker is not value — it's a trap.
- **Betting AGAINST a tanking team is fine** — but the market usually already prices this in, so edge is smaller.
- **When a tanker faces another bad/depleted team:** assign LOW confidence automatically. Two bad teams = coin flip = skip.
- **Tanking team's stats are inflated** by early-season games when they were trying. Discount season-long stats by 5-10% for current form.

### Step 9: Weather (outdoor sports only)
- High wind/snow: -2 to -5% for passing teams

### Step 10: Coaching matchups
- Significant coaching edge: +2 to +5%

### Step 11: Referee tendencies
- Notable tendency aligned with market: +/- 1 to 3%

### Step 12: Regression to the mean
- 8+ game streaks: adjust 3-5% toward season average

### Step 13: Adjustment Budget Check (MANDATORY)
Before finalizing your estimate, add up ALL adjustments from Steps 2-12:

- **If you used a model base rate (Step 2b):** Total adjustments must NOT exceed +/-15 percentage points from the model. The model already incorporates most public information — large deviations mean you think you know more than KenPom/BPI/ELO, and historically we don't.
- **If you used a hardcoded base rate (Step 1):** Total adjustments must NOT exceed +/-10 percentage points. Hardcoded rates are rough approximations — conservative adjustments are safer.

Example: KenPom says 55%. Your adjustments total +20%. Cap at +15%, so final estimate = 70%, not 75%.

Show the math: "Base: 55% | Adjustments: injury -8%, form +5%, H2H +3%, rest +2% = +2% net | Pre-cap: 57% | Budget check: 2% within 15% cap → OK | Final: 57%"

### Fallback Base Rates (use ONLY when model-based lookup in Step 2b fails)
| Situation | Base Rate |
|-----------|-----------|
| NBA home favorite | 67% |
| NBA road favorite | 60% |
| NFL home favorite (3+ pts) | 65% |
| NFL road favorite | 55% |
| MLB home team | 54% |
| NHL home team | 55% |
| College basketball home (power conf) | 65-70% |
| Soccer home win (top European) | 45% |
| Soccer draw | 27% |
| Soccer away win | 28% |
| UFC favorite | 65% |

### Data Sources
See `tools/data_sources.md` for complete URLs, Firecrawl JSON schemas, and search query templates per sport.

### Tennis-Specific Rules

Tennis has the WORST calibration in the system (HIGH confidence Brier: 0.310, N=87). Apply these corrections:

1. **HARD CAP: NEVER estimate >80% for ANY tennis match.** Grand Slam finals between #1 and a qualifier can go to 85%, but nothing else. Even top-5 players lose 20%+ of matches against ranked opponents. This cap is non-negotiable — Rybakina (93%), Sinner (96%), and Medvedev (85%) ALL lost when we ignored this.
2. **Surface matters enormously.** A clay specialist on hard court is NOT the same player. Always check surface-specific win rates via `firecrawl_scrape` on ATP/WTA player page.
3. **Current form > ranking.** A top-10 player on a losing streak is NOT a 90% favorite. Check last 5 match results.
4. **Lucky losers and qualifiers win 20-30% of first-round matches.** Do not assume they are automatic losses.
5. **H2H in tennis is more predictive than in team sports.** If 4+ prior matches exist, weight H2H at +/-5-8% instead of the general +/-2-5%.
6. **Ranking gaps lie.** A #11 vs #318 match is NOT 95%. Protected rankings, comeback players, and young talent mean the actual upset rate is 8-15% even for huge ranking gaps.

### Soccer-Specific Rules

Soccer has a systematic -11% underestimation bias (N=87, measured Feb 2026). Apply these corrections:

1. **ALWAYS estimate the draw probability first.** In evenly matched games, P(draw) = 25-30%. In mismatched games, P(draw) = 15-20%. Subtract P(draw) from 100% before splitting between the two teams.
2. **UCL knockout first legs are cagey.** P(draw) in UCL first legs is 30-35%. Reduce both teams' win probabilities accordingly.
3. **Home advantage in European leagues is a 10-15% win probability boost**, not the 5% many assume. Check xG home/away splits on FBref.
4. **Squad rotation in domestic cups.** Teams in UCL weeks often rotate heavily for midweek league/cup games. Always check if it is a cup match and whether the team played 3 days prior.

### NCAA Basketball-Specific Rules

NCAA Basketball has a persistent overestimation bias. Apply these corrections:

1. **Defer to `data/calibration_feedback.txt` for the current NCAA bias number.** As of March 2026, the bias is +7% (N=79). Apply this correction to your FINAL estimate (after all adjustments), not to the raw anchor. This value updates as more data comes in — always use the latest.
2. **KenPom/Barttorvik win probabilities are already calibrated.** If you find a model prediction, use it directly as your base rate and apply SMALLER adjustments (max +/-5% total from model). Do NOT inflate model numbers. If KenPom says teams are #9 vs #10, your estimate should be close to 50/50 — not 74/26.
3. **Home court in college is stronger than NBA.** Power conference home teams win 65-70%. This is already reflected in model predictions — do not double-count it.
4. **Conference games are tighter than non-conference.** Teams know each other well — upset rates are higher than rankings suggest. If teams are within 10 spots in KenPom, cap edge at 10%.
5. **"Trap games" are real in college.** A ranked team playing a mid-major after a big win is a classic letdown spot. Adjust -3 to -5%.
6. **50% markets are NOT "stale" — they represent genuine uncertainty.** When a Kalshi NCAA market sits at 50%, do not assume it's mispriced due to low liquidity. Check the `liquidity_tier` field: if "low", cap confidence at MEDIUM and require 12% EV.

---

## Economics Markets (10-Step Checklist)

### Step 1: Identify the indicator
- GDP, CPI, Fed rate, unemployment, payrolls, etc.
- Is it headline vs core? MoM vs YoY? What threshold?

### Step 2: Consensus forecast
- Bloomberg/Wall Street consensus. This is your base rate.
- Tight forecast range = less surprise probability

### Step 3: Prior release data
- Last 3-6 readings. Trend: accelerating, decelerating, stable?
- Typical surprise magnitude for this indicator

### Step 4: Leading indicators
- **GDP**: Atlanta Fed GDPNow, NY Fed Nowcast, retail sales, trade balance
- **CPI**: Cleveland Fed nowcast, PPI, energy prices, shelter trends
- **Fed Rate**: CME FedWatch (rarely surprises — 95%+ match expectations)
- **Payrolls**: ADP report, weekly claims, ISM employment
- **Jobless Claims**: Prior week, 4-week average, seasonal patterns

### Step 5: Recent economic data
- Consistent picture or mixed signals?

### Step 6: External shocks
- Tariffs, oil shocks, supply chain, natural disasters

### Step 7: Seasonal patterns
- January CPI high, Q1 GDP weak, holiday hiring

### Step 8: Revision history
- GDP revises ±0.3pp. Payrolls revise ±26K. CPI rarely revised.

### Step 9: Map consensus to threshold
- Consensus 2.5% GDP and question asks "above 2.0%?" → high YES probability
- Consensus near threshold → closer to 50/50

### Step 10: Sanity check with base rates

### Surprise Base Rates
| Indicator | Beat | Miss | Inline |
|-----------|------|------|--------|
| CPI (MoM) | 30% | 30% | 40% |
| GDP (advance) | 35% | 35% | 30% |
| Payrolls (±25K) | 35% | 35% | 30% |
| Fed rate | <5% surprise | <5% surprise | >95% as expected |
| Unemployment | 25% differ | | 75% match |

### Data Sources
See `tools/data_sources.md` for complete URLs, Firecrawl JSON schemas, and search query templates per economic indicator.

**Use `firecrawl_scrape` on nowcast pages** (GDPNow, Cleveland Fed, CME FedWatch) — these provide the most up-to-date base rates for economics markets. See data_sources.md for exact URLs and schemas.

---

## Output Format

For each market, provide:
```
Market: [question]
Base rate: X%
Adjustments: [factor] +/-Y%, [factor] +/-Y%, ...
Final estimate: Z%
Confidence: high/medium/low
Key evidence: [sources]
Key uncertainty: [what could swing it]
```

---

## EV Calculation (after all estimates)

After researching ALL markets, read `data/latest_scan.json` for prices, then calculate:

```
Edge = AI_estimate - market_price           (for YES bets)
Edge = market_price - AI_estimate           (for NO bets)
Fee  = 0.07 × price × (1 - price)          (Kalshi fee formula)
EV   = Edge - Fee

Kelly fraction = Edge / (1 - market_price) × 0.25    (YES)
Kelly fraction = Edge / market_price × 0.25           (NO)

Recommended bet = Kelly fraction × confidence_mult × bankroll
Max single bet = 3% of bankroll
Confidence multipliers: HIGH = 0.6x, MEDIUM = 0.8x, LOW = 0.3x (never bet)
```

Only recommend bets that pass the **Bet Gating Rules** above (minimum 8% EV for high and medium confidence, never for low, never if estimate is 42-58%).

---

## Pre-Research: Read Calibration Feedback (MANDATORY)

Before researching ANY market, read `data/calibration_feedback.txt`. If it exists, you MUST apply the bias corrections to your base rates before starting research. For example, if it says "Soccer: underestimate by 51%", raise all soccer base rates accordingly. This is not optional.

---

## Calibration Reminders (Updated: N=258 resolved markets, March 2026)

**Current performance:** Brier 0.218 (target <0.18) | Hit rate 51% | P&L -$52.49

- When you say 70%, it should happen ~70% of the time
- Individual game outcomes are noisy — even the best NBA teams lose 25% of games
- **HARD CAP: Never estimate above 75% for ANY sport.** When we estimate 70-80%, events only happen 67% of the time. Above 80%, only 55%. Overconfidence at extremes is the most documented bias in forecasting. The only exception is economics markets where nowcast models provide direct probability inputs (e.g., CME FedWatch 97% → use it).
- Extreme probabilities (>80% or <20%) require very strong evidence — but even with strong evidence, cap at 75%
- "Must-win" and "wants it more" narratives are worth 1-2% at most
- Recent hot/cold streaks are largely noise — regress toward season averages
- **HIGH confidence has the WORST Brier (0.243, N=62) — worse than MEDIUM (0.206, N=167).** Only assign HIGH confidence when you have ALL THREE: (a) a model-backed base rate (Step 2b), (b) structured injury data confirming the estimate, AND (c) your final estimate is within 10% of the model base rate. If ANY of these is missing, cap at MEDIUM. HIGH confidence now gets 0.6x Kelly (LESS than MEDIUM's 0.8x) because our confidence signal is inversely correlated with accuracy.
- **When your estimate is >75%, sanity-check:** "What is the realistic upset probability?" In tennis it is ALWAYS at least 20%. In soccer the draw alone is 20-30%. In NBA a bottom team beats a top team 20-30% of the time.
- **NO bets are better calibrated** (Brier 0.203) than YES bets (0.236). When in doubt, bet against something happening.
- **Sport biases: ALWAYS defer to `data/calibration_feedback.txt`** for the latest values. Do not use hardcoded bias numbers from this file — the calibration feedback is more current.
- **Liquidity matters.** If `liquidity_tier` is "low", cap confidence at MEDIUM and require 12% EV minimum. Low-liquidity markets have stale prices — the apparent "edge" is often phantom.

---

## Bet Gating Rules (STRICT)

These rules determine whether a bet is recommended, regardless of EV:

### 1. Low Confidence = No Bet
If your confidence is "low", NEVER recommend the bet. No exceptions. If you're not sure, you don't bet.

### 2. Confidence-Based EV Thresholds
| Confidence | Minimum EV Required |
|------------|-------------------|
| High       | 8%                |
| Medium     | 8%                |
| Low        | Never bet         |

### 3. No Coin-Flip Bets
If your probability estimate is between 42% and 58%, do NOT recommend the bet. Period. In 48 resolved markets in this zone, hit rate was 35.4% — worse than random. When we don't have a clear directional opinion, we have no edge. Skip it and move to markets where we have conviction.

### 4. Head-to-Head Sample Minimum
If fewer than 5 head-to-head games exist between teams/players in the last 2 years, cap the H2H adjustment at +/-1% only. Do not make large adjustments from small samples.

### 5. NO Bet Preference (Tiebreaker)
When two bets have similar EV (within 2%), prefer the NO direction. NO bets have Brier 0.205 vs YES bets at 0.280 (N=87). We are measurably better at identifying what WON'T happen than what will. This is a tiebreaker, not a hard rule — a YES bet with clearly higher EV still wins.

### 6. Never Bet ON Tanking Teams
Never place a YES bet on a team that is actively tanking (see Step 8b). Even if the price looks cheap and the opponent is depleted, tanking teams have a motivation deficit that makes their true win probability lower than stats suggest. We lost $7.20 betting BKN YES at 9¢ vs a depleted OKC — the stats said it was value, but Brooklyn had no reason to win. Betting AGAINST tankers is fine when EV is there.
