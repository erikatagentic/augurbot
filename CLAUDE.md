# CLAUDE.md — AugurBot

> Single-source-of-truth for AI agents building AugurBot.
> Every architectural decision is documented. Follow this file exactly.

---

## 0. Current Status

**All phases complete. App is live and deployed.**

| Component | Status | URL |
|-----------|--------|-----|
| Frontend | Deployed | https://augurbot-eonbjliar-heyagentic.vercel.app |
| Backend | Deployed | https://augurbot-production.up.railway.app |
| Database | Provisioned | https://vpcgzforjhcoxottoxxv.supabase.co |
| GitHub | Public repo | https://github.com/erikatagentic/augurbot |

**Verified working:** Full pipeline tested end-to-end — 100 Manifold markets fetched, 6 AI estimates generated (Sonnet + Opus model selection), 4 recommendations created with correct EV/Kelly calculations.

**Recent additions:**
- **CORS + connectivity fix**: CORS updated to use `allow_origin_regex=r"^http://localhost:\d+$"` so any localhost port works in dev. `.env.local` now points to Railway backend (`https://augurbot-production.up.railway.app`). `.env.production` created (gitignored) — Vercel env var `NEXT_PUBLIC_API_URL` must be set in dashboard. Full Playwright audit verified all 5 pages + all buttons working with zero console errors.
- **Toast notifications + error handling**: All mutation handlers (Scan Now, Check Resolutions, Sync Now, Log Trade, Refresh Estimate, Resolve Market, Settings save) now have try/catch with `sonner` toast feedback. Settings slider updates debounced (300ms) with rollback on failure. Backend `PUT /config` returns full updated config instead of `{"status": "updated"}`.
- **Trade sync from platforms**: Auto-import positions from Polymarket (wallet address, no auth) and Kalshi (RSA-PSS signed API). Deduplication via unique partial index. `trade_sync_log` table tracks sync runs. Settings UI with toggle, wallet input, sync button, and per-platform status.
- **Kalshi RSA-PSS auth**: Migrated from deprecated cookie-based Bearer tokens to per-request RSA-PSS signing. Legacy fallback still supported. New endpoints: `fetch_fills()`, `fetch_positions()`.
- **Resolution detection**: Auto-detect when markets resolve via platform APIs, close trades with P&L, populate performance_log for calibration tracking. Manual resolve button on market detail. Zero API cost (platform HTTP reads only).
- **Trade tracking**: Manual trade logging, open positions, trade history, portfolio stats, AI vs actual comparison
- **Cost optimization**: Once-daily scan (24h default), 25 markets/platform, 3 web searches/call, prompt caching, disabled price checks. Reduced from ~$25-60/day to ~$1/day.
- **Cost tracking**: `cost_log` table + `/performance/costs` endpoint + Settings page cost card
- **Kalshi-only sports focus**: Scanner now targets Kalshi sports markets only. Max close date tightened from 30d to 24h for daily short-term bets. Parlay detection filters out multi-leg markets.
- **Outcome labels**: Stores Kalshi's `yes_sub_title` as `outcome_label` in DB (e.g. "Chelsea", "Tie"). UI shows "Bet: Chelsea" instead of "YES" for clarity.
- **Kalshi market links**: External link on recommendation cards to open Kalshi sports page.
- **Auto-trade via Kalshi API**: One-click "Place Bet" button with confirmation dialog on recommendation cards. Auto-trade toggle in Settings — automatically places bets when scans find high-EV opportunities. Uses `KalshiClient.place_order()` with RSA-PSS auth.
- **Scan progress animation**: Real-time progress indicator during scans. Backend tracks progress in-memory (`scan_progress.py`), frontend polls `GET /scan/progress` every 2s. Shows animated progress bar, ETA, current market being analyzed, and running counters. 409 guard prevents concurrent scans.
- **Notifications (email + Slack)**: `notifier.py` sends alerts after scans find high-EV bets. Email via Resend API (dark-themed HTML + plain text), Slack via incoming webhook. Configurable min EV threshold (default 8%). Includes auto-trade details when trades are placed. Settings UI with toggle, email/webhook inputs, "Send Test" button. Endpoint: `POST /notifications/test`.
- **Configurable close-date window**: Settings slider (12h–72h, step 6h) instead of hardcoded 24h. Backend reads `max_close_hours` from config. Default remains 24h for daily sports focus.
- **Kalshi deep-link URLs**: `getKalshiMarketUrl()` now returns `kalshi.com/markets/{ticker}` instead of generic `/sports`. Clickable from recommendation cards and notifications.
- **Configurable scan schedule**: `scan_times` config key stores a list of hours (Pacific Time) when scans run. Default: `[8, 14]` (8 AM + 2 PM PT). Settings UI shows toggleable time-slot chips. `reconfigure_scan_schedule()` in `scheduler.py` uses APScheduler's `reschedule_job` to update dynamically without restart. `PUT /config` with `scan_times` triggers reconfiguration.
- **Auto-trade sweep notifications**: When the post-scan sweep places trades on existing active recommendations, email + Slack notifications are sent via `send_sweep_notifications()` in `notifier.py`. Distinct from scan notifications — subject says "sweep trades placed" instead of "high-EV bets found".
- **Auto-trade details in notifications**: When auto-trade is enabled and a bet is placed during a scan, notifications include trade details (contracts, price, amount) in all channels — email, Slack, and plain text.
- **P&L time-series chart**: `GET /performance/pnl-history` returns cumulative P&L data points over time. Performance page chart now shows real dated data points instead of a 2-point stub. Uses `get_pnl_timeseries()` in database.py.
- **Mobile navigation**: Hamburger menu (visible below `lg` breakpoint) opens shadcn Sheet drawer with all 5 nav links. `mobile-nav.tsx` + updated `header.tsx`.
- **Next scan countdown**: Health endpoint returns `next_scan_at` from APScheduler. Dashboard scan status shows "Next in Xh Ym" after last scan time.
- **Last scan summary card**: In-memory `save_scan_summary()` / `get_last_scan_summary()` in `scan_progress.py`. Dashboard shows markets found, researched, recommendations, and duration. Endpoint: `GET /scan/last-summary`.
- **Sport-by-sport accuracy**: `GET /performance/by-category` joins `performance_log` with `markets` to group by category. Self-fetching chart component on Performance page.
- **Daily digest email/Slack**: `send_daily_digest()` in `notifier.py` queries today's recommendations, trades, resolutions, P&L, and cost. Sends at 9 PM PT via APScheduler cron. Skips if no activity. Toggle in Settings: "Daily Digest (9 PM PT)". Config: `daily_digest_enabled`.
- **Model switch (Opus to Sonnet default)**: Default model changed from `claude-opus-4-6` ($15/$75 per MTok) to `claude-sonnet-4-5-20250929` ($3/$15 per MTok) for ~63% token cost savings. Settings toggle "Use Premium Model (Opus)" lets you switch back. Config: `use_premium_model`. High-value markets ($100K+ volume) and manual deep dives still auto-escalate to Opus.
- **Batch API for scheduled scans**: Scheduled scans (8 AM + 2 PM PT) use Anthropic Message Batches API for 50% off token costs. Pipeline refactored into `_prepare_market()` (upsert + cache check + Haiku screen) and `_finalize_market()` (store estimate + EV calc + recommend + auto-trade). `estimate_batch()` in `researcher.py` submits all markets as one batch, polls every 30s (max 2h timeout), then finalizes all results. Manual "Scan Now" stays sync for instant results. Automatic sync fallback if batch fails. Web search works in batch mode.

- **Simulated P&L tracking**: `performance_log` now has `simulated_pnl` column. When markets resolve, `resolve_market_trades()` computes what the Kelly-sized bet would have returned using `calculate_pnl()` from the recommendation data. Backfill endpoint: `POST /performance/backfill-simulated-pnl`. P&L chart shows dual lines (simulated purple + actual dashed green). StatsGrid shows "Simulated P&L" instead of "Total P&L". `avg_edge` now calculated from real data (was hardcoded 0.0). Duplicate performance_log guard prevents double-insertion on retry. `recommendation_id` now linked in performance_log. AccuracyByCategory supports date range filtering.
- **Upgraded sports prediction prompts**: Complete rewrite of `system_sports.txt` (119→203 lines). New anchor-and-adjust methodology forces Claude to start from a sport-specific base rate, list each factor with an explicit +/- adjustment, and show the math. 12-step checklist (was 9): added coaching/tactical matchups, referee tendencies, and regression-to-mean. Includes recommended data sources per sport (Basketball Reference, FanGraphs, KenPom, etc.). Reasoning expanded from 200-300 to 400-600 words. Web search limit increased from 3→5 uses per market. Research template now provides prioritized search strategy (injuries first, then stats, then matchup context).
- **Kalshi price capture fix**: `normalize_market()` was using `yes_ask` which returns 0 for thin/fresh sports markets. New `_best_price_cents()` helper uses fallback chain: `last_price` → bid/ask midpoint → `yes_ask` → `yes_bid` → 0. Scanner now skips markets with price_yes = 0 (no valid price). Previously, zero-price markets inflated edge calculations and corrupted simulated P&L.
- **Server-side close-date filtering**: `fetch_markets()` now passes `min_close_ts` and `max_close_ts` to Kalshi's API, so only markets closing within the configured window are returned. Previously, fetching ALL open markets meant paginating through thousands of irrelevant far-future markets and missing near-term game markets entirely. Also added `_NON_SPORT_KEYWORDS` exclusion list to prevent weather/finance/entertainment markets from being misdetected as sports.
- **Cancelled order detection**: Auto-trades now save `order_id` as `platform_trade_id` (format: `order_{id}`). Trade sync reconciles open trades against Kalshi's order status — if an order was cancelled on Kalshi (e.g. Erik manually cancels), the trade is auto-marked as "cancelled" with pnl=0. Uses `KalshiClient.fetch_orders(status="canceled")` + `_reconcile_kalshi_orders()` in `trade_syncer.py`. Runs during every trade sync (4h when enabled, or manual `POST /trades/sync`).
- **Order-to-fill duplicate prevention**: Auto-trade creates `order_{id}` trade, then fill sync creates `fill_{id}` for the same bet — previously resulted in 2 trades. Now `find_order_trade_for_fill()` in `database.py` matches fills to existing order trades by market_id + direction + status=open, and updates the order trade with fill data instead of inserting a duplicate.
- **Resolution notifications**: Email + Slack alerts when markets resolve. `send_resolution_notifications()` in `notifier.py` sends batch notification with per-market outcome, AI estimate vs actual, Brier score, and P&L (green for wins, red for losses). Summary shows record (W/L), total P&L, and simulated P&L. Triggered from `check_resolutions()` in scanner.py.
- **Expired recommendation cleanup**: Hourly `expire_stale_recs` job in scheduler.py runs `expire_stale_recommendations()` from database.py. Marks active recommendations as "expired" when their market's close_date has passed, so dashboard only shows tradeable opportunities.
- **Bankroll auto-update**: After markets resolve, `recalculate_bankroll()` in database.py computes `initial_bankroll + cumulative_closed_trade_pnl` and updates the bankroll config. Kelly sizing now uses current capital instead of static $10K. New `initial_bankroll` config key preserves the starting capital.
- **Scan error recovery**: `reset_stale_scan()` in scan_progress.py clears stuck `is_running=True` state on startup. Called from `main.py` lifespan. If process crashes mid-scan, next startup auto-resets so new scans aren't blocked by the 409 guard.
- **Exposure limits**: Auto-trade now checks aggregate portfolio exposure (`max_exposure_fraction`, default 25% of bankroll) and per-event exposure (`max_event_exposure_fraction`, default 10%) before placing any bet. Prevents over-deployment when many markets pass EV threshold. Event grouping uses Kalshi ticker prefix (e.g. `KXNBAGSW-26FEB14` groups all outcomes for one game). Applied in both `_finalize_market()` and `_sweep_untraded_recs()`. New DB functions: `get_total_open_exposure()`, `get_event_exposure()`, `extract_kalshi_event_id()`.
- **Scan failure alerts**: Email + Slack notifications when scheduled jobs fail. `send_failure_notification()` in notifier.py sends red-themed error alert with exception details. Called from scanner.py `execute_scan()` exception handler + scheduler.py wrappers for scan, resolution check, and trade sync jobs. Non-fatal — if notification fails, it logs and continues.
- **Config validation**: `ConfigUpdateRequest` in schemas.py now uses Pydantic `Field()` validators on all numeric fields. Invalid values (e.g. `kelly_fraction=-1`, `bankroll=0`) return 422 Unprocessable Entity automatically. Ranges: kelly 0-50%, edge 1-50%, bankroll >0, scan interval 1-168h, max close 6-168h.
- **429 rate limit retry**: `_is_retryable()` in http_utils.py now retries HTTP 429 (rate limit) responses with exponential backoff, in addition to 5xx server errors and connection failures.
- **Partial fill aggregation**: Trade syncer now aggregates multiple Kalshi fills into a single trade instead of creating duplicates. `platform_trade_id` stays as `order_X` (never replaced with `fill_Y`). Fill amounts/shares/fees are summed, entry price is weighted average. Fill IDs tracked in `notes` field (`[fill_X]` tags) for dedup on re-sync.
- **Economics category**: AugurBot now scans Kalshi economics markets (GDP, CPI, Fed rate, unemployment, payrolls, etc.) alongside sports. Economics detection via series ticker matching (`KXGDP`, `KXCPI`, `KXFED`, etc.) + keyword fallback. Category-specific prompts: `system_economics.txt` (anchor-and-adjust for macro data, 10-step research checklist, indicator-specific guidance, recommended data sources like FRED/BEA/BLS/Atlanta Fed GDPNow) + `research_economics.txt`. Economics-aware Haiku screener filters out obvious/trivial markets. `categories_enabled` config key with Settings UI toggles for Sports and Economics. `BlindMarketInput` now carries `economic_indicator` field (e.g. "GDP", "CPI"). Scanner reads `categories_enabled` from config and passes to Kalshi client. GDP markets have $2.6M+ volume; economics terms removed from `_NON_SPORT_KEYWORDS` to allow detection. Close-date window widens to 30 days when economics enabled (sports stays tight at configured hours). Economics markets exempt from volume filter (like sports).

**Scheduler:** APScheduler running (configurable scan times defaulting to 8 AM + 2 PM PT using batch mode, 1h resolution check, trade sync every 4h when enabled, daily digest 9 PM PT when notifications enabled, hourly stale rec cleanup, price checks disabled by default). Scan schedule is dynamically reconfigurable from Settings UI.

---

## 1. Project Overview

| Field | Value |
|-------|-------|
| **App Name** | AugurBot |
| **Purpose** | Personal edge-detection tool for prediction markets |
| **Owner** | Erik (erik@heyagentic.ai) |
| **Core Loop** | Fetch markets → AI research (blind to prices) → Estimate probability → Compare to market → Recommend highest-EV bets with Kelly sizing |
| **Platforms** | Kalshi (primary, sports + economics). Polymarket/Manifold code exists but is bypassed. |
| **Scope** | Personal tool — no auth, no multi-tenancy, no billing |

### How It Works (One Sentence)

The app scans prediction markets, has Claude research each question **without seeing the current odds**, compares Claude's independent probability estimate to the market price, and surfaces bets where the expected value exceeds a configurable threshold.

### Why This Works

- LLMs now match or exceed crowd forecasting accuracy (Brier score 0.096 for 3-model ensemble vs 0.121 for general public)
- Claude Opus returned 29% in a live 17-day Polymarket trading test (1st place vs GPT and Gemini)
- $40M+ in arbitrage profits documented from Polymarket mispricings (April 2024–April 2025)
- Combinatorial mispricings (logically related markets) have less bot competition than simple arbitrage

### Critical Architectural Rule

> **NEVER expose current market prices to the AI during the research/estimation phase.**
>
> Academic research shows GPT-4.5 had 0.994 correlation with provided market prices — it simply copies them.
> The AI receives ONLY: question text, resolution criteria, close date, and category.
> Market prices are introduced ONLY in the comparison step AFTER the AI outputs its estimate.

---

## 2. Tech Stack

### Setup Commands

```bash
# ── Frontend (Next.js) ──
pnpm create next-app@latest predictive-market-coach \
  --typescript --tailwind --eslint --app --src-dir=false \
  --import-alias "@/*" --use-pnpm --yes

cd predictive-market-coach

pnpm add framer-motion lucide-react clsx tailwind-merge recharts date-fns sonner
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button card badge separator tabs table dialog select input

# ── Backend (Python) ── (separate directory)
mkdir -p backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn httpx anthropic supabase python-dotenv apscheduler pydantic
```

### Stack Details

| Layer | Technology | Version | Reasoning |
|-------|-----------|---------|-----------|
| Frontend | Next.js (App Router) | 16.1.6 | Vercel-native, App Router |
| Language (FE) | TypeScript (strict) | 5.x | Type safety |
| Styling | Tailwind CSS v4 | latest | CSS-first config via `@theme inline {}`, no tailwind.config.js |
| Components | shadcn/ui | latest | Consistent with existing projects |
| Charts | Recharts via shadcn/ui chart | latest | Lightweight, React-native charting |
| Animation | Framer Motion | latest | Subtle UI transitions only |
| Icons | Lucide React | latest | Tree-shakeable |
| Notifications | Sonner | latest | Toast notifications for mutation feedback |
| Data Fetching | SWR | latest | Stale-while-revalidate with auto-refresh |
| Backend | Python + FastAPI | 3.12 / 0.128 | Best for data pipelines, scheduling, numerical work |
| AI | Anthropic Claude API | claude-sonnet-4-5-20250929 | Best forecasting performance; Opus for high-stakes |
| Database | PostgreSQL via Supabase | latest | Hosted Postgres, free tier |
| Scheduling | APScheduler (Python) | 3.x | Cron-like job scheduling in the backend process |
| Frontend Deploy | Vercel | — | erik@heyagentic.ai (erikatagentic) account |
| Backend Deploy | Railway | — | erik@heyagentic.ai account, persistent process |
| Package Manager | pnpm (FE) / pip (BE) | latest | Consistent with existing projects |

### Environment Variables

```bash
# ── Frontend (.env.local) ──
NEXT_PUBLIC_API_URL=http://localhost:8000           # Local dev; Vercel prod uses Railway URL
NEXT_PUBLIC_SITE_URL=https://augurbot.com

# ── Backend (.env) ──
ANTHROPIC_API_KEY=sk-ant-...                        # Claude API key
SUPABASE_URL=https://vpcgzforjhcoxottoxxv.supabase.co
SUPABASE_SERVICE_KEY=sb_secret_...                  # Supabase service role key
POLYMARKET_API_URL=https://clob.polymarket.com
POLYMARKET_GAMMA_URL=https://gamma-api.polymarket.com  # Market discovery API
KALSHI_API_URL=https://api.elections.kalshi.com/trade-api/v2
KALSHI_EMAIL=                                       # Kalshi login (legacy, optional)
KALSHI_PASSWORD=                                    # Kalshi password (legacy, optional)
KALSHI_API_KEY=                                     # Kalshi RSA API key ID (recommended)
KALSHI_PRIVATE_KEY_PATH=                            # Path to RSA private key PEM file
POLYMARKET_WALLET_ADDRESS=                          # Polygon wallet for trade sync (0x...)
MANIFOLD_API_URL=https://api.manifold.markets
RESEND_API_KEY=                                     # Resend.com API key for email notifications
```

---

## 3. Data Sources — Prediction Market APIs

### 3.1 Polymarket (Primary)

| Field | Value |
|-------|-------|
| Base URL | `https://clob.polymarket.com` |
| Auth | HMAC signatures for trading; public for market data |
| Rate Limit | 100 req/min (free), 1,000/hr (basic) |
| Data | Markets, events, prices (bestBid/bestAsk), volume, open interest, historical time series |
| Blockchain | Polygon (Chain ID 137) |

**Key Endpoints:**
- `GET /markets` — List all markets with metadata
- `GET /events` — Event groupings (an event can have multiple markets)
- `GET /prices` — Current price snapshots
- `GET /markets/{id}/history?startTs=X&endTs=Y` — Historical price data

**Client Library:** `py-clob-client` (official Python SDK)

### 3.2 Kalshi (Secondary — US Regulated)

| Field | Value |
|-------|-------|
| Base URL | `https://trading-api.kalshi.com/trade-api/v2` |
| Auth | Cookie-based API keys, **tokens expire every 30 minutes** |
| Rate Limit | Account-based |
| Data | Series, events, markets, order books, portfolio |

**Key Endpoints:**
- `GET /markets` — Market listings (supports `min_close_ts`, `max_close_ts`, `event_ticker`, `series_ticker` query params)
- `GET /events` — Event data
- `GET /markets/{ticker}/orderbook` — Order book (only bids shown; YES/NO reciprocity)

**Close-date filtering:** `GET /markets` accepts `min_close_ts` and `max_close_ts` (Unix timestamps, int64) for server-side date filtering. Without these, pagination returns markets in arbitrary order and near-term games get buried under thousands of far-future markets. Scanner passes these params to only fetch markets within the configured close-date window.

**Note:** Kalshi token expiry requires re-login every 30 minutes. Build a token refresh wrapper.

**Price fields:** Markets return `yes_bid`, `yes_ask`, `no_bid`, `no_ask`, `last_price` (all in cents 0-100). Thin/fresh markets return 0 for ALL price fields (never null). Use `_best_price_cents()` in `kalshi.py` for reliable price extraction.

### 3.3 Manifold Markets (Development & Testing)

| Field | Value |
|-------|-------|
| Base URL | `https://api.manifold.markets` |
| Auth | API key for writes; none for reads |
| Rate Limit | **500 req/min** (very generous) |
| Data | Markets, probabilities, users, comments, bets |

**Key Endpoints:**
- `GET /markets` — All markets (sorted by creation date)
- `GET /market/{id}` — Single market with probability
- `POST /bet` — Place bets (play money — safe for testing)

**Use for:** Prototyping the full pipeline without financial risk.

### 3.4 Metaculus (Supplementary Reference)

| Field | Value |
|-------|-------|
| Base URL | `https://www.metaculus.com/api/` |
| Type | Forecasting platform (not a betting market) |
| Data | Question metadata, community forecast distributions, resolution data |

**Use for:** Cross-referencing AI estimates against community superforecaster aggregates.

---

## 4. Core Architecture

### 4.1 System Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        PYTHON BACKEND (FastAPI)                      │
│                                                                      │
│  ┌────────────┐   ┌────────────────┐   ┌─────────────────────────┐  │
│  │  Market     │──▶│  AI Research   │──▶│  EV Calculator          │  │
│  │  Scanner    │   │  Pipeline      │   │  + Kelly Sizer          │  │
│  │            │   │  (BLIND mode)  │   │                         │  │
│  │  Polymarket │   │  Claude API    │   │  Compare AI estimate    │  │
│  │  Kalshi     │   │  Web Search    │   │  vs market price        │  │
│  │  Manifold   │   │  No prices!    │   │  Calculate EV + Kelly   │  │
│  └────────────┘   └────────────────┘   └─────────────────────────┘  │
│         │                │                         │                  │
│         ▼                ▼                         ▼                  │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    PostgreSQL (Supabase)                      │    │
│  │  markets │ snapshots │ ai_estimates │ recommendations │ perf  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌────────────┐                                                      │
│  │  Scheduler  │  APScheduler: scan every 4 hours, re-estimate      │
│  │  (Cron)     │  when market moves > 5% from last snapshot         │
│  └────────────┘                                                      │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              │  REST API (JSON)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     NEXT.JS FRONTEND (Vercel)                        │
│                                                                      │
│  ┌────────────┐  ┌───────────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ Dashboard   │  │ Market Detail  │  │ Explorer │  │ Performance │  │
│  │ (top bets)  │  │ (AI reasoning) │  │ (browse) │  │ (accuracy)  │  │
│  └────────────┘  └───────────────┘  └──────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Data Flow — The Blind Estimation Pipeline

**Step 1: Market Scan** (Python)
```
For each platform:
  1. Fetch active markets with >$10K volume (filter noise)
  2. Store/update market metadata in `markets` table
  3. Snapshot current price + volume in `market_snapshots` table
  4. Queue markets for AI research (skip if estimated within last 6 hours)
```

**Step 2: AI Research** (Python + Claude API)
```
For each queued market:
  1. Build research prompt with ONLY:
     - Question text
     - Resolution criteria
     - Close date
     - Category/tags
     - NO market price, NO volume, NO other market data
  2. Call Claude with web search (tool_use) to gather current evidence
  3. Require structured output:
     - 400-600 word reasoning (anchor-and-adjust methodology with explicit factor scoring)
     - Probability estimate (0.00 to 1.00)
     - Confidence level (high / medium / low)
     - Key evidence sources
     - Key uncertainties
  4. Store in `ai_estimates` table
```

**Step 3: EV Calculation** (Python)
```
For each new AI estimate:
  1. Fetch latest market price from `market_snapshots`
  2. Calculate edge = ai_probability - market_price
  3. Calculate EV = edge - platform_fees
  4. If EV > min_edge_threshold (default 5%):
     a. Calculate Kelly fraction = edge / (1 - market_price)
     b. Apply fractional Kelly (default 33%)
     c. Create recommendation in `recommendations` table
  5. If EV < threshold: mark as "no edge" and skip
```

**Step 4: Dashboard Display** (Next.js)
```
1. Fetch recommendations from backend API
2. Display sorted by EV (highest first)
3. Show: question, platform, market price, AI estimate, edge, Kelly size
4. Link to market detail with full AI reasoning
```

---

## 5. AI Research Prompt Design

### 5.1 System Prompt

```
You are a calibrated forecaster. Your job is to estimate the probability of
an event resolving YES or NO on a prediction market.

RULES:
1. You will NOT be shown the current market price. Estimate independently.
2. Research the question using web search to find current, relevant evidence.
3. Consider multiple scenarios and their likelihoods.
4. Use base rates from similar historical events when available.
5. Be explicit about your key uncertainties.
6. Output a probability between 0.01 and 0.99 (never 0.00 or 1.00).
7. Your reasoning MUST come before your probability estimate.

You will be evaluated on calibration: when you say 70%, it should happen ~70% of the time.
```

### 5.2 User Prompt Template

```
QUESTION: {question_text}

RESOLUTION CRITERIA: {resolution_criteria}

CLOSE DATE: {close_date}

CATEGORY: {category}

Please research this question and provide your forecast.

Respond in this exact JSON format:
{
  "reasoning": "Your 200-300 word analysis...",
  "probability": 0.XX,
  "confidence": "high" | "medium" | "low",
  "key_evidence": ["source 1", "source 2", ...],
  "key_uncertainties": ["uncertainty 1", "uncertainty 2", ...]
}
```

### 5.3 Model Selection Strategy

Default: **Sonnet** (~$0.05/estimate). Premium toggle or high-value volume auto-escalates to **Opus** (~$0.15/estimate).

| Scenario | Model | Reasoning |
|----------|-------|-----------|
| Standard scan (default) | claude-sonnet-4-5-20250929 | Best cost/performance ratio |
| Premium toggle ON | claude-opus-4-6 | User-selected via Settings |
| High-value markets (>$100K volume) | claude-opus-4-6 | Maximum accuracy for high-stakes |
| Re-estimation after odds move | claude-sonnet-4-5-20250929 | Frequent, cost-sensitive |
| Manual deep dive | claude-opus-4-6 | User-triggered, accuracy priority |
| Scheduled scan (batch mode) | Same as above | 50% off token costs via Batch API |

### 5.4 Web Search Integration

Use Claude's tool_use with a web search tool to allow the AI to actively research:
- Recent news about the event
- Historical base rates for similar events
- Expert opinions and analysis
- Polling data (for political markets)
- Statistical data (for sports/economic markets)

---

## 6. Expected Value & Position Sizing

### 6.1 EV Formula

For a YES position at market price `P_market`:
```
Edge = P_true - P_market
EV = Edge - Fees

Where:
  P_true  = AI's estimated probability
  P_market = Current market price (0 to 1)
  Fees    = Platform fee rate (Polymarket ~2%, Kalshi ~5-7%, Manifold 0%)
```

For a NO position:
```
Edge = (1 - P_true) - (1 - P_market) = P_market - P_true
EV = Edge - Fees
```

The system recommends YES when `P_true > P_market + fees` and NO when `P_true < P_market - fees`.

### 6.2 Kelly Criterion

```
Full Kelly = Edge / (1 - P_market)     # for YES bets
Full Kelly = Edge / P_market           # for NO bets

Recommended bet = Full Kelly * Kelly_fraction * Bankroll

Where:
  Kelly_fraction = 0.33 (default, configurable 0.25–0.50)
  Bankroll = user-configured total capital
```

### 6.3 Confidence Adjustment

Reduce Kelly fraction based on AI confidence:

| Confidence | Kelly Multiplier | Effective Kelly (at 0.33 base) |
|-----------|-----------------|-------------------------------|
| High | 1.0x | 33% |
| Medium | 0.6x | 20% |
| Low | 0.3x | 10% |

### 6.4 Thresholds

| Parameter | Default | Configurable |
|-----------|---------|-------------|
| Minimum edge | 5% | Yes (1%–20%) |
| Minimum volume | $10,000 | Yes ($1K–$100K) |
| Kelly fraction | 33% | Yes (25%–50%) |
| Max single bet | 5% of bankroll | Yes (1%–10%) |
| Re-estimate trigger | 5% market move | Yes (2%–10%) |

---

## 7. Database Schema

### PostgreSQL (Supabase)

```sql
-- Markets tracked across all platforms
CREATE TABLE markets (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform        TEXT NOT NULL CHECK (platform IN ('polymarket', 'kalshi', 'manifold', 'metaculus')),
  platform_id     TEXT NOT NULL,
  question        TEXT NOT NULL,
  description     TEXT,
  resolution_criteria TEXT,
  category        TEXT,
  close_date      TIMESTAMPTZ,
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed', 'resolved')),
  outcome         BOOLEAN,                    -- NULL until resolved, TRUE=YES, FALSE=NO
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(platform, platform_id)
);

-- Price snapshots over time
CREATE TABLE market_snapshots (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  price_yes       NUMERIC(5,4) NOT NULL,      -- 0.0000 to 1.0000
  price_no        NUMERIC(5,4),               -- usually 1 - price_yes
  volume          NUMERIC(15,2),              -- total volume in USD
  liquidity       NUMERIC(15,2),              -- current liquidity
  captured_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_snapshots_market_time ON market_snapshots(market_id, captured_at DESC);

-- AI probability estimates
CREATE TABLE ai_estimates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  probability     NUMERIC(5,4) NOT NULL,      -- AI's estimated probability (0.01 to 0.99)
  confidence      TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
  reasoning       TEXT NOT NULL,              -- AI's full reasoning (200-300 words)
  key_evidence    JSONB,                      -- array of evidence sources
  key_uncertainties JSONB,                    -- array of uncertainty factors
  model_used      TEXT NOT NULL,              -- e.g. 'claude-sonnet-4-5-20250929'
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_estimates_market_time ON ai_estimates(market_id, created_at DESC);

-- Bet recommendations (only when edge > threshold)
CREATE TABLE recommendations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  estimate_id     UUID NOT NULL REFERENCES ai_estimates(id),
  snapshot_id     UUID NOT NULL REFERENCES market_snapshots(id),
  direction       TEXT NOT NULL CHECK (direction IN ('yes', 'no')),
  market_price    NUMERIC(5,4) NOT NULL,      -- price at time of recommendation
  ai_probability  NUMERIC(5,4) NOT NULL,      -- AI estimate at time of recommendation
  edge            NUMERIC(5,4) NOT NULL,      -- absolute edge
  ev              NUMERIC(5,4) NOT NULL,      -- edge minus fees
  kelly_fraction  NUMERIC(5,4) NOT NULL,      -- recommended fraction of bankroll
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'resolved')),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_recommendations_active ON recommendations(status, ev DESC) WHERE status = 'active';

-- Performance tracking (populated when markets resolve)
CREATE TABLE performance_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id       UUID NOT NULL REFERENCES markets(id),
  recommendation_id UUID REFERENCES recommendations(id),
  ai_probability  NUMERIC(5,4) NOT NULL,
  market_price    NUMERIC(5,4) NOT NULL,
  actual_outcome  BOOLEAN NOT NULL,           -- TRUE = YES resolved, FALSE = NO resolved
  pnl             NUMERIC(10,4),              -- profit/loss if bet was placed
  brier_score     NUMERIC(5,4) NOT NULL,      -- (probability - outcome)^2
  resolved_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Trade tracking (manual and future API sync)
CREATE TABLE trades (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  market_id         UUID NOT NULL REFERENCES markets(id) ON DELETE CASCADE,
  recommendation_id UUID REFERENCES recommendations(id),
  platform          TEXT NOT NULL CHECK (platform IN ('polymarket','kalshi','manifold')),
  direction         TEXT NOT NULL CHECK (direction IN ('yes','no')),
  entry_price       NUMERIC(5,4) NOT NULL,
  amount            NUMERIC(15,2) NOT NULL,
  shares            NUMERIC(15,4),
  status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','cancelled')),
  exit_price        NUMERIC(5,4),
  pnl               NUMERIC(10,4),
  fees_paid         NUMERIC(10,4) DEFAULT 0,
  notes             TEXT,
  source            TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','api_sync')),
  platform_trade_id TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  closed_at         TIMESTAMPTZ
);

-- API cost tracking
CREATE TABLE cost_log (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_id         TEXT,
  market_id       UUID REFERENCES markets(id),
  model_used      TEXT NOT NULL,
  input_tokens    INT NOT NULL DEFAULT 0,
  output_tokens   INT NOT NULL DEFAULT 0,
  estimated_cost  NUMERIC(10,6) NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- User configuration
CREATE TABLE config (
  key             TEXT PRIMARY KEY,
  value           JSONB NOT NULL,
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 8. Backend API (Python FastAPI)

### 8.1 Project Structure

```
backend/
├── main.py                    # FastAPI app, CORS, lifespan, health/config endpoints
├── config.py                  # pydantic-settings BaseSettings from .env
├── requirements.txt           # Python dependencies (pip freeze)
├── schema.sql                 # Full Supabase SQL schema (6 tables + 2 RPC functions + default config)
├── .env                       # Environment variables (not committed)
├── routers/
│   ├── __init__.py
│   ├── markets.py             # /markets endpoints
│   ├── recommendations.py     # /recommendations endpoints
│   ├── trades.py              # /trades endpoints (CRUD, portfolio, AI comparison)
│   ├── performance.py         # /performance endpoints (+ /performance/costs)
│   └── scan.py                # /scan trigger endpoint
├── services/
│   ├── __init__.py
│   ├── polymarket.py          # Polymarket API client (Gamma + CLOB APIs)
│   ├── kalshi.py              # Kalshi API client (25-min token refresh)
│   ├── manifold.py            # Manifold API client (no auth, play money)
│   ├── researcher.py          # Claude AI blind research pipeline
│   ├── calculator.py          # EV + Kelly calculations (pure math)
│   ├── scanner.py             # Pipeline orchestrator (fetch → research → recommend)
│   ├── scan_progress.py       # In-memory scan progress tracker (polled by frontend)
│   ├── notifier.py            # Email (Resend) + Slack (webhook) notifications after scans
│   ├── trade_syncer.py        # Trade sync from Polymarket + Kalshi APIs
│   └── scheduler.py           # APScheduler job definitions (daily 8 AM PT cron)
├── models/
│   ├── __init__.py
│   ├── schemas.py             # ~20 Pydantic models including BlindMarketInput
│   └── database.py            # Supabase client singleton + ~20 data access functions
└── prompts/
    ├── system.txt             # System prompt for Claude
    └── research.txt           # Research prompt template
```

### 8.2 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scan` | Trigger a full market scan + AI research pipeline |
| `POST` | `/scan/{platform}` | Scan a single platform |
| `GET` | `/scan/progress` | Real-time scan progress (polled every 2s during active scans) |
| `GET` | `/scan/last-summary` | Summary of most recent completed scan (markets found/researched/recommended, duration) |
| `POST` | `/resolutions/check` | Check all active markets for resolution (zero cost) |
| `GET` | `/markets` | List tracked markets (filterable by platform, category, status) |
| `GET` | `/markets/{id}` | Market detail with latest estimate + price history |
| `GET` | `/markets/{id}/estimates` | All AI estimates for a market (with reasoning) |
| `GET` | `/markets/{id}/snapshots` | Price history for a market |
| `POST` | `/markets/{id}/refresh` | Re-research a specific market |
| `POST` | `/markets/{id}/resolve` | Manually resolve a market (closes trades, populates performance) |
| `GET` | `/recommendations` | Active recommendations sorted by EV |
| `GET` | `/recommendations/history` | Past recommendations with outcomes |
| `POST` | `/trades` | Log a new trade (auto-calculates shares) |
| `GET` | `/trades` | List trades (filterable by status, platform) |
| `GET` | `/trades/open` | Open positions only |
| `GET` | `/trades/portfolio` | Portfolio stats (unrealized P&L from latest snapshots) |
| `GET` | `/trades/comparison` | AI vs actual performance comparison |
| `GET` | `/trades/{id}` | Single trade with market |
| `PATCH` | `/trades/{id}` | Update/close/cancel a trade (auto-calculates P&L) |
| `DELETE` | `/trades/{id}` | Delete open/cancelled trade |
| `POST` | `/trades/sync` | Trigger trade sync from connected platforms (background) |
| `GET` | `/trades/sync/status` | Last sync status per platform |
| `POST` | `/trades/execute` | Place a bet on Kalshi from a recommendation (one-click trade) |
| `GET` | `/performance` | Aggregate stats: accuracy, Brier score, P&L, calibration |
| `GET` | `/performance/calibration` | Calibration curve data (bucketed) |
| `GET` | `/performance/costs` | API cost summary (today, week, month, all time) |
| `GET` | `/performance/pnl-history` | Cumulative P&L time-series (date-filterable) |
| `GET` | `/performance/by-category` | Hit rate and Brier score per sport category |
| `GET` | `/config` | Current configuration values |
| `PUT` | `/config` | Update configuration (thresholds, Kelly fraction, etc.) |
| `POST` | `/notifications/test` | Send test notification to verify email/Slack config |
| `GET` | `/health` | Backend health + last scan time |

### 8.3 CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://localhost:\d+$",
    allow_origins=[
        "https://augurbot.com",
        "https://www.augurbot.com",
        "https://augurbot-eonbjliar-heyagentic.vercel.app",
        "https://augurbot-heyagentic.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 9. Frontend (Next.js)

### 9.1 File Structure

```
augurbot/                         # Local dir: CC-predictive-market-coach
├── app/
│   ├── globals.css               # Tailwind v4 + dark theme via @theme inline {}
│   ├── layout.tsx                # Root layout (Inter + Instrument Serif, dark)
│   ├── page.tsx                  # Dashboard (default view)
│   ├── markets/
│   │   ├── page.tsx              # Market explorer
│   │   └── [id]/
│   │       └── page.tsx          # Market detail (uses `use(params)` for Next.js 16)
│   ├── performance/
│   │   └── page.tsx              # Performance & calibration
│   └── settings/
│       └── page.tsx              # Configuration
├── components/
│   ├── ui/                       # shadcn/ui components (auto-generated)
│   ├── layout/
│   │   ├── sidebar.tsx           # App sidebar (AugurBot branding)
│   │   ├── header.tsx            # Page header with actions
│   │   └── page-container.tsx    # Consistent page wrapper
│   ├── dashboard/
│   │   ├── top-recommendations.tsx
│   │   ├── recent-resolutions.tsx
│   │   ├── portfolio-summary.tsx
│   │   └── scan-status.tsx
│   ├── markets/
│   │   ├── market-table.tsx
│   │   └── market-filters.tsx
│   ├── detail/
│   │   ├── ai-reasoning.tsx
│   │   ├── price-chart.tsx
│   │   ├── estimate-history.tsx
│   │   ├── position-calculator.tsx
│   │   └── edge-indicator.tsx
│   ├── performance/
│   │   ├── calibration-chart.tsx
│   │   ├── brier-score-card.tsx
│   │   ├── pnl-chart.tsx
│   │   └── accuracy-by-category.tsx
│   └── shared/
│       ├── ev-badge.tsx           # Color-coded EV indicator
│       ├── platform-badge.tsx     # Colored dot + platform name
│       ├── confidence-badge.tsx   # High/Medium/Low badge
│       ├── loading-skeleton.tsx
│       └── empty-state.tsx
├── hooks/
│   ├── use-markets.ts            # SWR hooks for market data
│   ├── use-recommendations.ts    # SWR hooks + scan trigger
│   └── use-performance.ts        # SWR hooks for perf/config/health
├── lib/
│   ├── api.ts                    # Centralized apiFetch<T>() + all API functions
│   ├── utils.ts                  # cn() helper + formatters
│   ├── constants.ts              # UI constants, labels, thresholds
│   ├── motion.ts                 # Framer Motion animation presets
│   └── types.ts                  # Shared TypeScript interfaces
└── public/
    └── favicon.ico
```

### 9.2 Pages

**Dashboard (`/`):**
- Portfolio summary card: total recommendations, win rate, total P&L
- Top 5 active recommendations sorted by EV (card grid)
- Recent resolutions with outcome (win/loss badges)
- Last scan timestamp + "Scan Now" button
- Quick stats: average Brier score, best category

**Market Explorer (`/markets`):**
- Filterable table: platform, category, status, EV range
- Columns: question (truncated), platform badge, market price, AI estimate, edge, EV, confidence
- Click row → market detail
- Search by keyword
- Sort by any column

**Market Detail (`/markets/[id]`):**
- Full question text + resolution criteria
- Side-by-side: market price vs AI estimate (large numbers)
- Edge indicator (color-coded bar)
- Position calculator: input bankroll → recommended bet size
- AI Reasoning panel: full 200-300 word analysis, evidence, uncertainties
- Price history chart (line chart with AI estimates overlaid as markers)
- Estimate history: list of past AI estimates for this market
- "Refresh Estimate" button

**Performance (`/performance`):**
- Calibration chart: expected probability (x) vs actual frequency (y), with perfect calibration line
- Brier score over time (line chart)
- Cumulative P&L chart (line chart)
- Accuracy breakdown by category (bar chart)
- Accuracy breakdown by platform (bar chart)
- Accuracy breakdown by confidence level (table)
- Total resolved markets, hit rate

**Settings (`/settings`):**
- Risk parameters: Kelly fraction slider, min edge threshold, max single bet
- Scan settings: frequency, min volume filter
- Platform toggles: enable/disable Polymarket, Kalshi, Manifold
- API status indicators (green/red for each platform + Claude)
- Manual scan trigger

---

## 10. Design System

### 10.1 Color Tokens

Dark theme only. Consistent with agentic-website design language.

```css
:root {
  /* ── Backgrounds ── */
  --background: hsl(240 6% 3.9%);
  --surface: hsl(240 5% 6.5%);
  --surface-raised: hsl(240 5.9% 10%);
  --surface-overlay: hsl(240 3.7% 15.9%);

  /* ── Text ── */
  --foreground: hsl(0 0% 98%);
  --foreground-muted: hsl(240 5% 64.9%);
  --foreground-subtle: hsl(240 4% 46%);

  /* ── Borders ── */
  --border: hsl(240 3.7% 15.9%);
  --border-hover: hsl(240 5.3% 26.1%);

  /* ── EV Indicators ── */
  --ev-positive: hsl(160 64% 52%);           /* #34D399 — green, edge > 10% */
  --ev-moderate: hsl(43 96% 56%);            /* #FBBF24 — yellow, edge 5-10% */
  --ev-neutral: hsl(240 5% 64.9%);           /* #A1A1AA — gray, edge < 5% */
  --ev-negative: hsl(0 91% 71%);             /* #F87171 — red, negative edge */

  /* ── Platform Colors ── */
  --platform-polymarket: hsl(255 92% 76%);   /* #A78BFA — purple */
  --platform-kalshi: hsl(217 91% 60%);       /* #3B82F6 — blue */
  --platform-manifold: hsl(160 64% 52%);     /* #34D399 — green */
  --platform-metaculus: hsl(43 96% 56%);     /* #FBBF24 — yellow */

  /* ── Confidence ── */
  --confidence-high: hsl(160 64% 52%);       /* green */
  --confidence-medium: hsl(43 96% 56%);      /* yellow */
  --confidence-low: hsl(0 91% 71%);          /* red */

  /* ── Accent ── */
  --primary: hsl(255 92% 76%);
  --primary-hover: hsl(258 90% 66%);
}
```

### 10.2 Typography

Same as agentic-website: Inter (body) + Instrument Serif (display numbers).

| Element | Classes |
|---------|---------|
| Page title | `text-2xl font-semibold` |
| Card title | `text-lg font-medium` |
| Stat number (large) | `text-4xl font-display italic` |
| Stat number (card) | `text-2xl font-semibold tabular-nums` |
| Body | `text-sm text-foreground-muted` |
| Label | `text-xs font-medium uppercase tracking-widest` |

### 10.3 Components

**EV Badge:**
- `> 10%` → green badge, text "Strong Edge"
- `5–10%` → yellow badge, text "Moderate Edge"
- `< 5%` → gray, not recommended (shouldn't appear in recommendations)
- `< 0%` → red badge, text "No Edge"

**Platform Badge:**
- Colored dot + platform name
- Polymarket (purple), Kalshi (blue), Manifold (green)

**Confidence Badge:**
- High → green outline, "High Confidence"
- Medium → yellow outline, "Medium"
- Low → red outline, "Low"

---

## 11. Implementation Phases

All phases are complete. Listed here for reference.

### Phase 1: Foundation — COMPLETE

1. ~~Scaffold Next.js project + Python backend directory~~
2. ~~Set up Supabase project, run SQL schema from Section 7~~
3. ~~Configure Tailwind v4 + dark theme tokens~~
4. ~~Build basic Next.js layout (sidebar, header, page container)~~
5. ~~Build FastAPI skeleton with health endpoint~~
6. ~~Create Polymarket API client (fetch markets, prices)~~
7. ~~Create Manifold API client (for testing)~~
8. ~~Wire up market fetching → Supabase storage~~

### Phase 2: AI Research Pipeline — COMPLETE

9. ~~Write Claude system prompt + research prompt template~~
10. ~~Build `researcher.py` — calls Claude API with blind estimation~~
11. ~~Build `calculator.py` — EV calculation + Kelly sizing~~
12. ~~Wire pipeline: fetch market → research → calculate → store recommendation~~
13. ~~Test full pipeline on 100 Manifold markets~~
14. ~~Add `/scan` and `/markets` endpoints to FastAPI~~

### Phase 3: Dashboard + Pages — COMPLETE

15. ~~Build dashboard page: top recommendations, recent resolutions, scan status~~
16. ~~Build market explorer: table, filters, search~~
17. ~~Build market detail: AI reasoning, price chart, position calculator~~
18. ~~Build EV badge, platform badge, confidence badge components~~
19. ~~Connect all pages to backend API~~
20. ~~Add "Scan Now" button + loading states~~

### Phase 4: Scheduling & Automation — COMPLETE

21. ~~Add APScheduler to backend: scan every 4 hours~~
22. ~~Add re-estimation trigger: re-research when market moves >5%~~
23. ~~Add Kalshi API client (optional, requires account credentials)~~

### Phase 5: Performance, Settings & Deploy — COMPLETE

24. ~~Build performance page: calibration chart, Brier score, P&L~~
25. ~~Build settings page: risk parameters, platform toggles~~
26. ~~Deploy: Vercel (frontend) + Railway (backend)~~

### Phase 6: Trade Tracking — COMPLETE

26. ~~Trades database table, backend models, CRUD endpoints~~
27. ~~Trade log dialog (pre-fill from recommendations), open positions widget~~
28. ~~Trade history table, portfolio stats page, AI vs actual comparison~~
29. ~~Integration across dashboard, market detail, performance pages~~

### Phase 7: Cost Optimization — COMPLETE

30. ~~Default once-daily scan (24h interval), price checks disabled~~
31. ~~Reduced to 25 markets/platform, 3 web searches/call, 20h estimate cache~~
32. ~~Prompt caching (expanded system prompt to ~1,200 tokens, cache_control enabled)~~
33. ~~Cost tracking: cost_log table, per-call logging, /performance/costs endpoint~~
34. ~~Settings UI: markets per platform, web searches, estimate cache, price check toggle, cost card~~

### Phase 8: Resolution Detection — COMPLETE

35. ~~Platform clients: `check_resolution()` + `check_resolutions_batch()` for Manifold, Polymarket, Kalshi~~
36. ~~Scanner: `check_resolutions()` orchestrator (polls platform APIs, triggers resolve pipeline)~~
37. ~~Scheduler: `resolution_check` job every 6h (zero Claude API cost)~~
38. ~~API: `POST /resolutions/check` + `POST /markets/{id}/resolve` endpoints~~
39. ~~Database: `resolve_recommendations()`, `cancel_trades_for_market()` functions~~
40. ~~Frontend: resolution check button in settings, manual resolve YES/NO on market detail~~

### Phase 9: Trade Sync from Platforms — COMPLETE

41. ~~Kalshi RSA-PSS auth migration (with legacy fallback) + `fetch_fills()` + `fetch_positions()`~~
42. ~~Polymarket Data API position fetching (wallet address, no auth)~~
43. ~~`trade_syncer.py` orchestrator: sync Polymarket positions + Kalshi fills, deduplication~~
44. ~~Database: `trade_sync_log` table + unique partial index on `(platform, platform_trade_id)`~~
45. ~~Scheduler: `sync_platform_trades` job (configurable interval, disabled by default)~~
46. ~~API: `POST /trades/sync` + `GET /trades/sync/status` endpoints~~
47. ~~Frontend: Trade Sync settings card (toggle, wallet input, Kalshi RSA status, sync button, status display)~~

### Phase 10: Notifications, Deep Links & Scheduling — COMPLETE

48. ~~Email + Slack notifications after scans (`notifier.py`, Resend API + webhook)~~
49. ~~Configurable close-date window (Settings slider 12h–72h, `max_close_hours` config key)~~
50. ~~Kalshi deep-link URLs (`kalshi.com/markets/{ticker}` instead of generic `/sports`)~~
51. ~~Daily 8 AM PT cron schedule (CronTrigger with `America/Los_Angeles` timezone)~~
52. ~~Auto-trade details in notifications (contracts, price, amount in email/Slack/text)~~
53. ~~Settings UI: NotificationSettings card (toggle, email, webhook, min EV slider, Send Test button)~~
54. ~~`POST /notifications/test` endpoint for verifying notification config~~

### Phase 11: Dashboard & UX Improvements — COMPLETE

55. ~~P&L time-series chart: `GET /performance/pnl-history` + `usePnLHistory()` hook + real cumulative chart~~
56. ~~Mobile nav: shadcn Sheet drawer with hamburger button (`mobile-nav.tsx` + `header.tsx`)~~
57. ~~Next scan countdown: `get_next_scan_time()` in scheduler + `next_scan_at` in health endpoint~~
58. ~~Last scan summary card: `save_scan_summary()` / `get_last_scan_summary()` + `GET /scan/last-summary` + dashboard component~~
59. ~~Sport-by-sport accuracy: `GET /performance/by-category` + self-fetching `AccuracyByCategory` component~~
60. ~~Daily digest: `send_daily_digest()` in notifier + 9 PM PT cron job + `daily_digest_enabled` config + Settings toggle~~

### Future Work (Prioritized Roadmap)

All major cost optimizations are complete (model switch, batch API, Haiku screening, configurable schedule, custom domain). Remaining ideas:

1. **Multi-model ensemble** — Average estimates from 2-3 models for better calibration (higher cost, better accuracy).
2. **Historical backtesting** — Replay past markets to measure model accuracy before/after changes.

---

## 11b. Cost Optimization

### Default Settings (Hobby Mode)

| Parameter | Default | Environment Variable |
|-----------|---------|---------------------|
| Scan interval | 24 hours | `SCAN_INTERVAL_HOURS=24` |
| Markets per platform | 25 | `MARKETS_PER_PLATFORM=25` |
| Min volume filter | $50,000 | `MIN_VOLUME=50000` |
| Web searches per call | 3 | `WEB_SEARCH_MAX_USES=3` |
| Estimate cache | 20 hours | `ESTIMATE_CACHE_HOURS=20` |
| Price check | Disabled | `PRICE_CHECK_ENABLED=false` |

### Cost Drivers

1. **Claude API calls**: Each market estimate uses Sonnet with web search (~$0.02-0.05/call)
2. **Web search tokens**: Search results add 2,000-5,000 input tokens per call
3. **Scan frequency**: More scans = more API calls
4. **Market count**: More markets per scan = more API calls

### Prompt Caching

System prompt expanded to ~1,200 tokens (above 1,024 minimum for caching). Includes:
- Calibration methodology, category guidance, pitfall avoidance
- JSON response format (moved from research template)
- Cache reads at 0.1x input rate after first call in a batch

### Cost Tracking

- `cost_log` table records every Claude API call with token counts and estimated cost
- `GET /performance/costs` returns today/week/month/all-time summaries
- Settings page shows live cost dashboard

### Batch API (Scheduled Scans)

Scheduled scans use Anthropic's Message Batches API for 50% off token costs:
- All markets prepared in parallel (upsert + Haiku screen)
- Single batch submitted to Anthropic (polls every 30s, max 2h timeout)
- All results finalized after batch completes
- Manual "Scan Now" stays sync for instant feedback
- Automatic sync fallback if batch fails

### Expected Costs

| Mode | Model | Batch? | Markets/Scan | Scans/Day | Est. Daily Cost |
|------|-------|--------|-------------|-----------|-----------------|
| Default (Sonnet + batch) | Sonnet | Yes | 25 | 2 | ~$1.25 |
| Premium (Opus + batch) | Opus | Yes | 25 | 2 | ~$4.50 |
| Manual scan (Sonnet) | Sonnet | No | 25 | 1 | ~$1.25 |
| Legacy (Opus, no batch) | Opus | No | 25 | 2 | ~$7.50 |

---

## 12. Code Standards

### Frontend (TypeScript / Next.js)

1. Named exports only. No default exports.
2. `strict: true` in tsconfig. No `any` type.
3. One component per file, kebab-case filenames.
4. Use `cn()` for conditional Tailwind classes.
5. Import Lucide icons individually.
6. All API calls through `lib/api.ts` client.
7. All display text in `lib/constants.ts` (labels, empty states, etc.).
8. Use SWR or React Query for data fetching with proper loading/error states.

### Backend (Python / FastAPI)

1. Type hints on all function signatures.
2. Pydantic models for all request/response schemas.
3. Async endpoints with `httpx.AsyncClient` for external API calls.
4. All configuration via environment variables (never hardcode secrets).
5. Structured logging with timestamps.
6. Error handling: never expose internal errors to frontend.
7. All prompts stored in `prompts/` directory as text files.

### Import Order (Frontend)

```typescript
// 1. React / Next.js
import { Suspense } from "react";
import Link from "next/link";

// 2. Third-party
import { AreaChart, Area, XAxis, YAxis } from "recharts";
import { TrendingUp, Search } from "lucide-react";

// 3. Internal components (UI first, then custom)
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EVBadge } from "@/components/shared/ev-badge";

// 4. Lib / utils
import { cn, formatPercent } from "@/lib/utils";
import { fetchRecommendations } from "@/lib/api";

// 5. Types
import type { Recommendation, Market } from "@/lib/types";
```

---

## 13. Deployment

### Frontend — Vercel

- Account: erik@heyagentic.ai (erikatagentic)
- URL: https://augurbot-eonbjliar-heyagentic.vercel.app
- Framework: Next.js (auto-detected)
- Build: `pnpm build`
- Env vars: `NEXT_PUBLIC_API_URL=https://augurbot-production.up.railway.app`, `NEXT_PUBLIC_SITE_URL=https://augurbot.com`
- Auto-deploys on push to `main` branch of erikatagentic/augurbot

### Backend — Railway

- Account: erik@heyagentic.ai
- URL: https://augurbot-production.up.railway.app
- Runtime: Python 3.12 (Nixpacks)
- Root directory: `backend`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Env vars: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, POLYMARKET_API_URL, POLYMARKET_GAMMA_URL, KALSHI_API_URL, MANIFOLD_API_URL, RESEND_API_KEY
- Persistent process (APScheduler runs in-process: daily 8 AM PT scan, 6h resolution check, 4h trade sync when enabled)
- Auto-deploys on push to `main` branch

### Database — Supabase

- Project: vpcgzforjhcoxottoxxv
- URL: https://vpcgzforjhcoxottoxxv.supabase.co
- Region: US East
- Schema: 6 tables + 2 RPC functions (see `backend/schema.sql`)
- Row Level Security: OFF (personal tool, single user)

### GitHub

- Repo: https://github.com/erikatagentic/augurbot (public)
- Account: erikatagentic (erik@heyagentic.ai)
- Note: Local git credential helper may use `eriklumos1` token — push with `gh auth token` embedded in URL if permission denied

---

## 14. What NOT To Do

| Anti-Pattern | Do Instead |
|-------------|-----------|
| Show market prices to AI during research | Blind estimation only |
| Use full Kelly sizing | Fractional Kelly (25-50%) |
| Recommend bets with < 5% edge | Filter out low-EV opportunities |
| Hardcode content in components | Read from `lib/constants.ts` |
| Use `any` type | Proper TypeScript interfaces |
| Import all Lucide icons | Import individually |
| Store API keys in code | Environment variables only |
| Build auth/billing | Personal tool — skip multi-tenancy |
| Add a light theme | Dark only |
| Trust AI estimates blindly | Track calibration, review reasoning |
| Bet on markets closing within 24 hours | Allow time for edge to materialize |
| Scan every minute | Every 4 hours (respect rate limits, save API costs) |
| Use raw `yes_ask` from Kalshi as market price | Use `_best_price_cents()` fallback chain; skip markets with price=0 |

---

## 15. Known Pitfalls & Gotchas

| Issue | Solution |
|-------|----------|
| Next.js 16: `useSearchParams()` requires `<Suspense>` boundary | Wrap component using `useSearchParams()` in `<Suspense>` |
| Next.js 16: Dynamic route `params` are async | Use `use(params)` pattern in page components |
| Tailwind v4: No `tailwind.config.js` | All theming via `@theme inline {}` in `globals.css` |
| SWR hooks: if page destructures `mutate`, hook must expose it | Ensure custom SWR hooks return `mutate` in their return object |
| `pnpm create next-app@latest .` fails with uppercase dirs | Scaffold to temp dir, copy back |
| `shadcn@latest init -y` still prompts | Use `--defaults` flag instead |
| Git push fails (eriklumos1 credential) | Use `gh auth token` embedded in remote URL |
| Supabase Python client is synchronous | Wrap blocking calls or use sync patterns in FastAPI |
| Polymarket needs TWO APIs | Gamma API for discovery, CLOB API for live prices |
| Kalshi tokens expire every 25 minutes | Auto-refresh wrapper in `kalshi.py` |
| Kalshi `yes_ask` = 0 on thin/fresh sports markets | `_best_price_cents()` uses `last_price` → midpoint → ask → bid fallback; scanner skips price=0 |
| Kalshi GET /markets returns arbitrary order without `close_ts` params | Always pass `min_close_ts`/`max_close_ts` to get near-term markets; without them, near-term games are buried under thousands of far-future markets |
| Kalshi weather/entertainment markets false-positive as sports | `_NON_SPORT_KEYWORDS` exclusion list in `kalshi.py` catches temperature, billboard, finance, etc. before sport keyword matching |
| Manifold `closeTime` is in milliseconds | Divide by 1000 for Python `datetime` |
| CORS blocks non-3000 localhost ports | Use `allow_origin_regex=r"^http://localhost:\d+$"` in CORSMiddleware |
| `.env.production` is gitignored by `.env*` pattern | Set `NEXT_PUBLIC_API_URL` in Vercel dashboard, not via file |
| React 19: `useRef()` requires initial value | Use `useRef<Type>(undefined)` not `useRef<Type>()` |

---

*End of CLAUDE.md*
