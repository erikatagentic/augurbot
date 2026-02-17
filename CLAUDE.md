# CLAUDE.md — AugurBot

> AI-powered prediction market edge detection, run entirely in Claude Code.

---

## What This Does

AugurBot finds mispriced bets on Kalshi (sports + economics). It fetches markets, you (Claude Code) research each one blind (without seeing prices), estimate probabilities, then compare to market prices to find +EV bets.

**Critical rule:** NEVER look at market prices during research. Read `data/blind_markets.json` only. Prices are revealed after all estimates.

---

## How to Scan

```bash
# 1. Fetch markets from Kalshi
python3 tools/scan.py                     # Default: 48h window, sports + economics
python3 tools/scan.py --hours 72          # Custom window
python3 tools/scan.py --categories sports # Sports only
```

This outputs:
- `data/latest_scan.json` — Full market data (with prices, for EV calc)
- `data/blind_markets.json` — Questions only (no prices, for research)
- `data/scans/YYYY-MM-DD_HHMM.json` — Archived scan

```bash
# 2. Research each market (Claude Code does this)
# Read data/blind_markets.json, follow tools/methodology.md
# Use web search for each market, apply anchor-and-adjust
# Output probability estimates

# 3. Calculate EV (after ALL estimates are done)
# Read data/latest_scan.json for prices
# Edge = AI estimate - market price
# Fee = 0.07 × price × (1-price)
# EV = Edge - Fee
# Recommend bets with EV >= 3%
```

## How to Bet

```bash
python3 tools/bet.py TICKER yes 50 65     # Buy 50 YES contracts at 65¢
python3 tools/bet.py TICKER no 25 40      # Buy 25 NO contracts at 40¢
python3 tools/bet.py --dry-run TICKER yes 50 65  # Auth check only
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
| `tools/methodology.md` | Full research playbook |
| `data/latest_scan.json` | Most recent scan (with prices) |
| `data/blind_markets.json` | Markets for research (no prices) |
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
tools/scan.py          → Fetches from Kalshi API, filters, deduplicates
Claude Code            → Researches each market (web search, blind)
EV calculation         → Compares AI estimate to market price
tools/bet.py           → Places orders on Kalshi
data/                  → Local JSON storage (scans, recommendations)
```

No backend server. No frontend. No database. No API costs.
Research is done by Claude Code directly (covered by subscription).

---

## Legacy Code

The `backend/` directory contains a full FastAPI backend and `app/` has a Next.js frontend. These were the original web app — they still work but are no longer deployed. The CLI tools in `tools/` replace them for daily use.
