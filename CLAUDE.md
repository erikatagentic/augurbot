# CLAUDE.md — AugurBot

> AI-powered prediction market edge detection, run entirely in Claude Code.

---

## What This Does

AugurBot finds mispriced bets on Kalshi (sports + economics). It fetches markets, you (Claude Code) research each one blind (without seeing prices), estimate probabilities, then compare to market prices to find +EV bets.

**Critical rule:** NEVER look at market prices during research. Read `data/blind_markets.json` only. Prices are revealed after all estimates.

---

## Slash Commands (Primary Workflow)

| Command | What it does |
|---------|-------------|
| `/project:scan` | Full scan: fetch markets, blind research, calculate EV, save recommendations |
| `/project:bet` | Place top 5 bets at 5% of balance each |
| `/project:balance` | Check Kalshi cash, portfolio, positions, resting orders |
| `/project:results` | Check resolutions, update performance, generate calibration feedback |

**Daily workflow:** `/project:scan` → review recs → `/project:bet` → wait → `/project:results`

**Self-improvement loop:** `/project:results` generates `data/calibration_feedback.txt` with bias corrections. Next `/project:scan` reads it and adjusts estimates accordingly.

## Manual Tools

```bash
# Fetch markets
backend/.venv/bin/python3 tools/scan.py                     # Default: 48h window
backend/.venv/bin/python3 tools/scan.py --hours 72          # Custom window
backend/.venv/bin/python3 tools/scan.py --categories sports # Sports only

# Place bets
backend/.venv/bin/python3 tools/bet.py TICKER yes 50 65     # Buy 50 YES at 65¢
backend/.venv/bin/python3 tools/bet.py TICKER no 25 40      # Buy 25 NO at 40¢
backend/.venv/bin/python3 tools/bet.py --dry-run TICKER yes 50 65

# Check balance
backend/.venv/bin/python3 tools/balance.py

# Check results (stats only, no API)
backend/.venv/bin/python3 tools/results.py --stats

# Check results (resolve markets via Kalshi API)
backend/.venv/bin/python3 tools/results.py
```

---

## Research Methodology

Full playbook: [tools/methodology.md](tools/methodology.md)

**Sports** — 12-step anchor-and-adjust:
1. Identify sport + base rate
2. Injury search (most impactful factor)
3. Recent form, H2H, home/away, schedule, stats
4. Adjustments: Star OUT = -8 to -15%, back-to-back = -4 to -6%, etc.

**Economics** — 10-step anchor-and-adjust:
1. Identify indicator + consensus forecast
2. Nowcasts (GDPNow, Cleveland Fed, CME FedWatch)
3. Leading indicators, external shocks
4. Map consensus to question threshold

---

## EV & Kelly Math

```
Edge = AI_estimate - market_price        (YES)
Edge = market_price - AI_estimate        (NO)
Fee  = 0.07 × price × (1 - price)       (Kalshi: max 1.75% at 50/50)
EV   = Edge - Fee

Kelly = Edge / (1 - price) × 0.33       (YES, fractional Kelly)
Kelly = Edge / price × 0.33             (NO)
Bet   = Kelly × bankroll                (default $10,000, cap at 5%)
```

Min EV threshold: 3%. Only recommend bets above this.

---

## Key Files

| File | Purpose |
|------|---------|
| `tools/scan.py` | Fetch markets from Kalshi API |
| `tools/bet.py` | Place orders on Kalshi |
| `tools/balance.py` | Check Kalshi balance + positions + resting orders |
| `tools/results.py` | Check resolutions, track performance, generate calibration feedback |
| `tools/methodology.md` | Full research playbook |
| `.claude/commands/scan.md` | Slash command: full scan + research workflow |
| `.claude/commands/bet.md` | Slash command: place top 5 bets |
| `.claude/commands/balance.md` | Slash command: quick balance check |
| `.claude/commands/results.md` | Slash command: results + self-improvement |
| `data/latest_scan.json` | Most recent scan (with prices) |
| `data/blind_markets.json` | Markets for research (no prices) |
| `data/recommendations.json` | All researched markets with AI estimates + EV |
| `data/bets.json` | Placed bets with order IDs and outcomes |
| `data/performance.json` | Aggregate stats (Brier, hit rate, P&L, bias) |
| `data/calibration_feedback.txt` | Bias corrections for future scans |
| `data/scans/` | Archived scans |
| `backend/services/kalshi.py` | Kalshi API client (auth, fetch, orders) |
| `backend/services/calculator.py` | EV + Kelly math |
| `backend/.env` | Kalshi credentials |

---

## Setup

Kalshi credentials in `backend/.env`:
```bash
KALSHI_API_KEY=your-api-key-id
KALSHI_PRIVATE_KEY_PATH=/path/to/private_key.pem
# OR inline:
KALSHI_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n..."
```

Run scripts with the backend venv:
```bash
backend/.venv/bin/python3 tools/scan.py
backend/.venv/bin/python3 tools/bet.py TICKER yes 10 65
```

Install dependencies (if venv is missing):
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install httpx cryptography tenacity pydantic-settings python-dotenv
```

---

## Architecture

```
/project:scan          → tools/scan.py → blind research → EV calc → data/recommendations.json
/project:bet           → data/recommendations.json → balance check → tools/bet.py → data/bets.json
/project:balance       → tools/balance.py → Kalshi API → display
/project:results       → tools/results.py → Kalshi API → data/performance.json → calibration_feedback.txt
                         ↑                                                              │
                         └──────────── calibration feedback injected into scan ──────────┘
```

No backend server. No frontend. No database. No API costs.
Research is done by Claude Code directly (covered by subscription).

---

## Legacy Code

The `backend/` directory contains a full FastAPI backend and `app/` has a Next.js frontend. These were the original web app — they still work but are no longer deployed. The CLI tools in `tools/` replace them for daily use.
