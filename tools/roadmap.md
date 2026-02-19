# AugurBot Roadmap — Future Improvements

> Ideas to implement after we have more resolved bets with the upgraded research pipeline.
> Prerequisite: ~80+ resolved bets with the new Firecrawl/model-based research (Phase 2).

---

## Completed

### Phase 1: Data Quality (Feb 2026)
- [x] Dedup resolved markets in performance.json (removed 11 duplicates)
- [x] Normalize sport types (NCAAB -> NCAA Basketball)
- [x] Performance breakdown by confidence level and bet direction
- [x] Brier trend tracking by scan batch
- [x] Bankroll snapshot history (data/bankroll_history.json)
- [x] `/project:positions` command (mark-to-market P&L on open bets)
- [x] Fix 404 ticker errors (bad tickers from AI-guessed names)

### Phase 2: Research Pipeline Upgrade (Feb 2026)
- [x] Firecrawl scraping for structured data (injuries, stats, ratings)
- [x] Model-based base rates (ESPN BPI, KenPom, ELO) replace hardcoded rates
- [x] 8-10 lookups per market (was 5)
- [x] 3 parallel research subagents (Stats/Model/News)
- [x] Tennis-specific rules (cap at 85%, surface, form > ranking)
- [x] Soccer-specific rules (draw probability first, UCL cagey legs)
- [x] Tightened HIGH confidence requirements (model + injury data required)
- [x] Data sources reference file (tools/data_sources.md)

---

## Phase 3: Strategy Optimization

### 3.1 Category ROI Analysis
- **Priority**: HIGH
- **Prerequisite**: 80+ resolved bets across categories
- **What**: Analyze which sports/categories actually produce positive ROI vs which lose money. If Tennis keeps bleeding despite the new rules, stop betting it entirely.
- **Implementation**: Add to results.py — per-category ROI calculation, recommendation to drop unprofitable categories.
- **Expected impact**: Eliminate losing categories, focus budget on winners. Could improve overall ROI by 10-20%.

### 3.2 Dynamic Kelly Sizing by Category
- **Priority**: HIGH
- **Prerequisite**: 80+ resolved bets with category-specific hit rates
- **What**: Instead of flat 0.33 Kelly fraction for everything, adjust per category. If NBA NO bets hit 60% but Tennis hits 30%, size them differently.
- **Implementation**: Update calculator.py — category-specific Kelly multipliers. Update methodology.md with dynamic sizing rules.
- **Expected impact**: Better capital allocation. Bigger bets on reliable categories, smaller on volatile ones.

### 3.3 Adversarial Review Agent
- **Priority**: HIGH
- **Prerequisite**: None (can implement anytime)
- **What**: Before finalizing an estimate, a second agent challenges it. "You said 75% for the Knicks — what about their 2-8 road record against top defenses?" Catches overconfident estimates.
- **Implementation**: Add step to scan.md — after initial estimate, dispatch a "Devil's Advocate" Task agent that tries to find evidence AGAINST the estimate. Adjust if valid counterargument found.
- **Expected impact**: Directly addresses the HIGH confidence problem (Brier 0.403). Could reduce extreme probability estimates and prevent catastrophic misses.

### 3.4 Automated Daily Scan via n8n
- **Priority**: MEDIUM
- **Prerequisite**: Phase 2 validated (Brier improvement confirmed)
- **What**: n8n workflow that triggers a daily scan + bet cycle at optimal time (morning for evening games). No manual intervention needed.
- **Implementation**: n8n workflow using Claude Code API or CLI trigger. Sends results to Slack.
- **Expected impact**: Consistency — never miss a day. More data faster.

### 3.5 Line Movement / Timing Analysis
- **Priority**: MEDIUM
- **Prerequisite**: 50+ bets with scan timestamps
- **What**: Track whether earlier or later scans produce better edge. If we scan at noon but the game is at 7pm, the line might move. Are we better off scanning earlier (more stale data but less efficient market) or later (fresher data but more efficient market)?
- **Implementation**: Add scan_time and game_time fields to recommendations. Analyze edge by time-to-game.
- **Expected impact**: Optimize scan timing for maximum edge.

### 3.6 Bet Outcome Attribution
- **Priority**: MEDIUM
- **Prerequisite**: 100+ resolved bets
- **What**: For each resolved bet, identify which research factor was most predictive and which was most misleading. Was the injury data accurate? Did the model base rate help? Did breaking news matter?
- **Implementation**: Add reasoning_factors field to recommendations. After resolution, tag which factors were right/wrong.
- **Expected impact**: Learn which data sources to trust more. Improve research weighting.

### 3.7 Market Type Specialization
- **Priority**: LOW
- **Prerequisite**: 150+ resolved bets
- **What**: Identify if we're systematically better at certain bet types. Are we better at game winners vs spreads? Props vs totals? Moneylines vs specials?
- **Implementation**: Track bet_type in recommendations. Analyze Brier/ROI per bet type.
- **Expected impact**: Focus on bet types where we have genuine edge.

### 3.8 Ensemble Estimates
- **Priority**: LOW
- **Prerequisite**: Phase 3.3 (adversarial agent) implemented
- **What**: Instead of one estimate, generate 3 independent estimates (different prompting strategies) and average them. Ensemble methods reduce variance in forecasting.
- **Implementation**: Dispatch 3 independent estimation agents with different anchoring strategies. Median or trimmed mean of their estimates.
- **Expected impact**: More robust estimates, fewer outlier predictions. Research shows ensembles improve Brier by 0.01-0.03.

### 3.9 Historical Calibration Curves
- **Priority**: LOW
- **Prerequisite**: 200+ resolved bets
- **What**: Plot actual outcomes vs predicted probabilities. If we say 70%, does it happen 70% of the time? Identify specific calibration buckets that are off.
- **Implementation**: Generate calibration curve data in results.py. Visual output or table showing predicted vs actual by decile.
- **Expected impact**: Precise identification of where we're overconfident vs underconfident. Fine-tune adjustments.

---

## Decision Criteria

Before implementing any Phase 3 item:
1. Run `/project:results` to check current Brier score
2. Confirm we have enough resolved bets (see prerequisite for each item)
3. Compare pre-Phase 2 Brier (0.287) vs post-Phase 2 Brier to validate the research upgrade worked
4. Prioritize items that address the biggest remaining weakness

## Current Baseline (Feb 19, 2026)
- Resolved bets: 41 (deduped)
- Overall Brier: 0.287
- Hit rate: 41%
- Actual P&L: +$3.25
- Worst tier: HIGH confidence (Brier 0.403)
- Worst category: Tennis (+15% overestimate), Soccer (-24% underestimate)
- Best trend: Brier improving scan-over-scan (0.282 -> 0.364 -> 0.150)
