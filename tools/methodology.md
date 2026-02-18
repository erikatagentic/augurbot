# AugurBot Research Methodology

> This file tells Claude Code how to research prediction markets.
> Follow this methodology exactly when analyzing markets from `data/blind_markets.json`.

---

## Critical Rule

**NEVER look at market prices during research.** Read only `data/blind_markets.json` (which has no prices). The AI must estimate probabilities independently. Prices are revealed only AFTER all estimates are complete, during the EV calculation step.

---

## Workflow

1. **Read** `data/blind_markets.json` — contains questions, categories, dates (NO prices)
2. **Research** each market using web search, following the category-specific checklist below
3. **Output** a probability estimate (0.01–0.99) for each market
4. **After ALL estimates**, read `data/latest_scan.json` to get prices and calculate EV

---

## Sports Markets (12-Step Checklist)

Use anchor-and-adjust: start from a base rate, apply adjustments, show the math.

### Step 1: Identify the market
- Sport (NBA, NFL, MLB, NHL, NCAA, Soccer, UFC, etc.)
- Bet type (winner, spread, over/under, prop)
- Look up the base rate below

### Step 2: Injury & roster status (CRITICAL — search first)
- Search latest injury report for BOTH teams
- Star OUT: -8 to -15% | Role player OUT: -2 to -5% | Questionable: -3 to -7%

### Step 3: Recent form (last 5-10 games)
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

### Base Rates (moneyline/winner)
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
- NBA: Basketball Reference, NBA.com/stats
- NFL: Pro Football Reference, Football Outsiders
- MLB: FanGraphs, Baseball Savant
- NHL: Hockey Reference
- College: KenPom, Barttorvik
- Soccer: FBref, Transfermarkt, Understat
- UFC: UFC Stats, Tapology

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
- FRED (fred.stlouisfed.org) — all major indicators
- BLS.gov — CPI, employment
- BEA.gov — GDP, PCE
- Atlanta Fed GDPNow
- Cleveland Fed inflation nowcast
- CME FedWatch
- Bloomberg/Reuters consensus

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
