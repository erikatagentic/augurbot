# CLAUDE.md — Predictive Market Coach

> Single-source-of-truth for AI agents building the Predictive Market Coach.
> Every architectural decision is documented. Follow this file exactly.

---

## 1. Project Overview

| Field | Value |
|-------|-------|
| **App Name** | Predictive Market Coach |
| **Purpose** | Personal edge-detection tool for prediction markets |
| **Owner** | Erik (erik@heyagentic.ai) |
| **Core Loop** | Fetch markets → AI research (blind to prices) → Estimate probability → Compare to market → Recommend highest-EV bets with Kelly sizing |
| **Platforms** | Polymarket (primary), Kalshi (secondary), Manifold Markets (dev/testing) |
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

pnpm add framer-motion lucide-react clsx tailwind-merge recharts date-fns
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
| Frontend | Next.js (App Router) | 15.x | Same stack as agentic-website, Vercel-native |
| Language (FE) | TypeScript (strict) | 5.x | Type safety |
| Styling | Tailwind CSS v4 | latest | CSS-first config, dark theme |
| Components | shadcn/ui | latest | Consistent with existing projects |
| Charts | Recharts | latest | Lightweight, React-native charting |
| Animation | Framer Motion | latest | Subtle UI transitions only |
| Icons | Lucide React | latest | Tree-shakeable |
| Backend | Python + FastAPI | 3.12+ / 0.115+ | Best for data pipelines, scheduling, numerical work |
| AI | Anthropic Claude API | claude-sonnet-4-5-20250929 | Best forecasting performance; Opus for high-stakes |
| Database | PostgreSQL via Supabase | latest | Hosted Postgres, real-time subscriptions, free tier |
| Scheduling | APScheduler (Python) | 3.x | Cron-like job scheduling in the backend process |
| Frontend Deploy | Vercel | — | erik@heyagentic.ai account |
| Backend Deploy | Railway | — | Python backend hosting with persistent process |
| Package Manager | pnpm (FE) / pip (BE) | latest | Consistent with existing projects |

### Environment Variables

```bash
# ── Frontend (.env.local) ──
NEXT_PUBLIC_API_URL=http://localhost:8000     # FastAPI backend URL
NEXT_PUBLIC_SITE_URL=https://predictive-market-coach.vercel.app

# ── Backend (.env) ──
ANTHROPIC_API_KEY=sk-ant-...                  # Claude API key
SUPABASE_URL=https://xxx.supabase.co          # Supabase project URL
SUPABASE_SERVICE_KEY=eyJ...                   # Supabase service role key
POLYMARKET_API_URL=https://clob.polymarket.com
KALSHI_API_URL=https://trading-api.kalshi.com/trade-api/v2
KALSHI_EMAIL=                                 # Kalshi login (optional)
KALSHI_PASSWORD=                              # Kalshi password (optional)
MANIFOLD_API_URL=https://api.manifold.markets
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
- `GET /markets` — Market listings
- `GET /events` — Event data
- `GET /markets/{ticker}/orderbook` — Order book (only bids shown; YES/NO reciprocity)

**Note:** Kalshi token expiry requires re-login every 30 minutes. Build a token refresh wrapper.

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
     - 200-300 word reasoning
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

| Scenario | Model | Reasoning |
|----------|-------|-----------|
| Standard scan (bulk) | claude-sonnet-4-5-20250929 | Best cost/performance ratio |
| High-value markets (>$100K volume) | claude-opus-4-6 | Maximum accuracy for high-stakes |
| Re-estimation after odds move | claude-sonnet-4-5-20250929 | Frequent, cost-sensitive |
| Manual deep dive | claude-opus-4-6 | User-triggered, accuracy priority |

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
├── main.py                    # FastAPI app, CORS, lifespan
├── config.py                  # Settings from env vars
├── requirements.txt           # Python dependencies
├── routers/
│   ├── markets.py             # /markets endpoints
│   ├── recommendations.py     # /recommendations endpoints
│   ├── performance.py         # /performance endpoints
│   └── scan.py                # /scan trigger endpoint
├── services/
│   ├── polymarket.py          # Polymarket API client
│   ├── kalshi.py              # Kalshi API client
│   ├── manifold.py            # Manifold API client
│   ├── researcher.py          # Claude AI research pipeline
│   ├── calculator.py          # EV + Kelly calculations
│   └── scheduler.py           # APScheduler job definitions
├── models/
│   ├── schemas.py             # Pydantic request/response models
│   └── database.py            # Supabase client + queries
└── prompts/
    ├── system.txt             # System prompt for Claude
    └── research.txt           # Research prompt template
```

### 8.2 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/scan` | Trigger a full market scan + AI research pipeline |
| `POST` | `/scan/{platform}` | Scan a single platform |
| `GET` | `/markets` | List tracked markets (filterable by platform, category, status) |
| `GET` | `/markets/{id}` | Market detail with latest estimate + price history |
| `GET` | `/markets/{id}/estimates` | All AI estimates for a market (with reasoning) |
| `GET` | `/markets/{id}/snapshots` | Price history for a market |
| `POST` | `/markets/{id}/refresh` | Re-research a specific market |
| `GET` | `/recommendations` | Active recommendations sorted by EV |
| `GET` | `/recommendations/history` | Past recommendations with outcomes |
| `GET` | `/performance` | Aggregate stats: accuracy, Brier score, P&L, calibration |
| `GET` | `/performance/calibration` | Calibration curve data (bucketed) |
| `GET` | `/config` | Current configuration values |
| `PUT` | `/config` | Update configuration (thresholds, Kelly fraction, etc.) |
| `GET` | `/health` | Backend health + last scan time |

### 8.3 CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://predictive-market-coach.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 9. Frontend (Next.js)

### 9.1 File Structure

```
predictive-market-coach/
├── app/
│   ├── globals.css               # Tailwind v4 + dark theme tokens
│   ├── layout.tsx                # Root layout (fonts, metadata)
│   ├── page.tsx                  # Dashboard (default view)
│   ├── markets/
│   │   ├── page.tsx              # Market explorer
│   │   └── [id]/
│   │       └── page.tsx          # Market detail
│   ├── performance/
│   │   └── page.tsx              # Performance & calibration
│   └── settings/
│       └── page.tsx              # Configuration
├── components/
│   ├── ui/                       # shadcn/ui components
│   ├── layout/
│   │   ├── sidebar.tsx           # App sidebar navigation
│   │   ├── header.tsx            # Page header with actions
│   │   └── page-container.tsx    # Consistent page wrapper
│   ├── dashboard/
│   │   ├── top-recommendations.tsx
│   │   ├── recent-resolutions.tsx
│   │   ├── portfolio-summary.tsx
│   │   └── scan-status.tsx
│   ├── markets/
│   │   ├── market-card.tsx
│   │   ├── market-table.tsx
│   │   ├── market-filters.tsx
│   │   └── platform-badge.tsx
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
│       ├── confidence-badge.tsx   # High/Medium/Low badge
│       ├── loading-skeleton.tsx
│       └── empty-state.tsx
├── hooks/
│   ├── use-markets.ts            # SWR/React Query for market data
│   ├── use-recommendations.ts
│   └── use-performance.ts
├── lib/
│   ├── api.ts                    # Backend API client
│   ├── utils.ts                  # cn() helper + formatters
│   ├── constants.ts              # UI constants, labels, thresholds
│   └── types.ts                  # Shared TypeScript types
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

Build in this exact sequence.

### Phase 1: Foundation (Days 1-2)

1. Scaffold Next.js project + Python backend directory
2. Set up Supabase project, run SQL schema from Section 7
3. Configure Tailwind v4 + dark theme tokens
4. Build basic Next.js layout (sidebar, header, page container)
5. Build FastAPI skeleton with health endpoint
6. Create Polymarket API client (fetch markets, prices)
7. Create Manifold API client (for testing)
8. Wire up market fetching → Supabase storage

### Phase 2: AI Research Pipeline (Days 3-4)

9. Write Claude system prompt + research prompt template
10. Build `researcher.py` — calls Claude API with blind estimation
11. Build `calculator.py` — EV calculation + Kelly sizing
12. Wire pipeline: fetch market → research → calculate → store recommendation
13. Test full pipeline on 5 Manifold markets (play money, no risk)
14. Add `/scan` and `/markets` endpoints to FastAPI

### Phase 3: Dashboard (Days 5-7)

15. Build dashboard page: top recommendations, recent resolutions, scan status
16. Build market explorer: table, filters, search
17. Build market detail: AI reasoning, price chart, position calculator
18. Build EV badge, platform badge, confidence badge components
19. Connect all pages to backend API
20. Add "Scan Now" button + loading states

### Phase 4: Scheduling & Automation (Day 8)

21. Add APScheduler to backend: scan every 4 hours
22. Add re-estimation trigger: re-research when market moves >5%
23. Add market resolution detection: update outcomes, calculate P&L
24. Add Kalshi API client (optional, if user has account)

### Phase 5: Performance & Calibration (Days 9-10)

25. Build performance page: calibration chart, Brier score, P&L
26. Build settings page: risk parameters, platform toggles
27. Populate `performance_log` from resolved markets
28. Calculate and display running Brier score
29. Build calibration curve (bucketed: 0-10%, 10-20%, ... 90-100%)
30. Deploy: Vercel (frontend) + Railway (backend)

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

- Account: erik@heyagentic.ai
- Framework: Next.js (auto-detected)
- Build: `pnpm build`
- Env vars: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`

### Backend — Railway

- Runtime: Python 3.12
- Start command: `uvicorn main:app --host 0.0.0.0 --port 8000`
- Env vars: all backend vars from Section 2
- Persistent process (APScheduler runs in-process)

### Database — Supabase

- Free tier: 500MB storage, 2 compute units
- Region: US East (closest to both Vercel and Railway)
- Enable Row Level Security: OFF (personal tool, single user)

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

---

*End of CLAUDE.md*
