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

### Step 9: Weather (outdoor sports only)
- High wind/snow: -2 to -5% for passing teams

### Step 10: Coaching matchups
- Significant coaching edge: +2 to +5%

### Step 11: Referee tendencies
- Notable tendency aligned with market: +/- 1 to 3%

### Step 12: Regression to the mean
- 8+ game streaks: adjust 3-5% toward season average

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

Tennis has the WORST calibration in the system (HIGH confidence Brier: 0.403). Apply these corrections:

1. **NEVER estimate >85% for ANY tennis match** unless it is a Grand Slam final between #1 and a qualifier. Lower-round matches have 15-25% upset rates even for heavy favorites.
2. **Surface matters enormously.** A clay specialist on hard court is NOT the same player. Always check surface-specific win rates via `firecrawl_scrape` on ATP/WTA player page.
3. **Current form > ranking.** A top-10 player on a losing streak is NOT a 90% favorite. Check last 5 match results.
4. **Lucky losers and qualifiers win 20-30% of first-round matches.** Do not assume they are automatic losses.
5. **H2H in tennis is more predictive than in team sports.** If 4+ prior matches exist, weight H2H at +/-5-8% instead of the general +/-2-5%.

### Soccer-Specific Rules

Soccer has a systematic -24% underestimation bias. Apply these corrections:

1. **ALWAYS estimate the draw probability first.** In evenly matched games, P(draw) = 25-30%. In mismatched games, P(draw) = 15-20%. Subtract P(draw) from 100% before splitting between the two teams.
2. **UCL knockout first legs are cagey.** P(draw) in UCL first legs is 30-35%. Reduce both teams' win probabilities accordingly.
3. **Home advantage in European leagues is a 10-15% win probability boost**, not the 5% many assume. Check xG home/away splits on FBref.
4. **Squad rotation in domestic cups.** Teams in UCL weeks often rotate heavily for midweek league/cup games. Always check if it is a cup match and whether the team played 3 days prior.

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

Kelly fraction = Edge / (1 - market_price) × 0.33    (YES)
Kelly fraction = Edge / market_price × 0.33           (NO)

Recommended bet = Kelly fraction × bankroll (default $10,000)
Max single bet = 5% of bankroll ($500)
```

Only recommend bets that pass the **Bet Gating Rules** above (minimum 5% EV for high confidence, 8% for medium, never for low; 12% if estimate is 42-58%).

---

## Pre-Research: Read Calibration Feedback (MANDATORY)

Before researching ANY market, read `data/calibration_feedback.txt`. If it exists, you MUST apply the bias corrections to your base rates before starting research. For example, if it says "Soccer: underestimate by 51%", raise all soccer base rates accordingly. This is not optional.

---

## Calibration Reminders

- When you say 70%, it should happen ~70% of the time
- Individual game outcomes are noisy — even the best NBA teams lose 25% of games
- Extreme probabilities (>85% or <15%) require very strong evidence
- "Must-win" and "wants it more" narratives are worth 1-2% at most
- Recent hot/cold streaks are largely noise — regress toward season averages
- Question CTAs and motivation narratives don't predict outcomes
- **HIGH confidence has been the WORST tier (Brier 0.403).** Only assign HIGH confidence when you have BOTH a model-backed base rate (from Step 2b) AND structured injury data confirming the estimate. If relying purely on web search narratives, cap at MEDIUM.
- **When your estimate is >80%, sanity-check:** "What is the realistic upset probability?" In tennis it is ALWAYS at least 15%. In soccer the draw alone is 20-30%. In NBA a bottom team beats a top team 20-30% of the time.

---

## Bet Gating Rules (STRICT)

These rules determine whether a bet is recommended, regardless of EV:

### 1. Low Confidence = No Bet
If your confidence is "low", NEVER recommend the bet. No exceptions. If you're not sure, you don't bet.

### 2. Confidence-Based EV Thresholds
| Confidence | Minimum EV Required |
|------------|-------------------|
| High       | 5%                |
| Medium     | 8%                |
| Low        | Never bet         |

### 3. Weak Estimate Filter
If your probability estimate is between 42% and 58% (essentially a coin flip), you need EV >= 12% to recommend it. In practice, this means you almost never bet coin flips. If you can't pick a clear side, skip it.

### 4. Head-to-Head Sample Minimum
If fewer than 5 head-to-head games exist between teams/players in the last 2 years, cap the H2H adjustment at +/-1% only. Do not make large adjustments from small samples.
