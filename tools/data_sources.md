# AugurBot Data Sources Reference

> Canonical URLs, Firecrawl JSON schemas, and search query templates per sport and economic indicator.
> Used by Claude Code during `/project:scan` research phase.
> Referenced by `tools/methodology.md` and `.claude/commands/scan.md`.

---

## How To Use These Sources

During research, use the MCP tools in this priority order:

1. **`firecrawl_scrape`** (JSON format) — For known URLs with structured data (stats pages, injury reports)
2. **`firecrawl_search`** — For open-ended queries where you need search + full page content (model lookups, H2H)
3. **`WebSearch`** — For fast, broad queries where snippets suffice (breaking news, context)

**Fallback chain:** If `firecrawl_scrape` fails on a URL → try `firecrawl_search` with the query template → fall back to `WebSearch`.

---

## NBA

### Injury Reports
- **URL**: `https://www.espn.com/nba/injuries`
- **Tool**: `firecrawl_scrape` with JSON format
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "teams": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "team": {"type": "string"},
            "injuries": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "player": {"type": "string"},
                  "position": {"type": "string"},
                  "status": {"type": "string"},
                  "details": {"type": "string"}
                }
              }
            }
          }
        }
      }
    }
  }
  ```
- **Fallback query**: `"{Team}" NBA injury report today site:espn.com OR site:cbssports.com`

### Team Stats & Ratings
- **URL**: `https://www.basketball-reference.com/teams/{ABBREV}/2026.html`
  - Common abbreviations: LAL, BOS, NYK, PHI, MIL, DEN, PHO, GSW, MEM, CLE, OKC, MIN, SAC, LAC, MIA, ATL, CHI, IND, ORL, DET, TOR, BRK, CHA, WAS, HOU, DAL, NOP, SAS, UTA, POR
- **Tool**: `firecrawl_scrape` with JSON format
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "record": {"type": "string"},
      "offensive_rating": {"type": "number"},
      "defensive_rating": {"type": "number"},
      "net_rating": {"type": "number"},
      "last_10": {"type": "string"},
      "streak": {"type": "string"},
      "home_record": {"type": "string"},
      "away_record": {"type": "string"}
    }
  }
  ```
- **Fallback query**: `"{Team}" NBA 2025-26 record stats offensive defensive rating`

### Win Probability Models
- **Tool**: `firecrawl_search`
- **Query**: `"{Team A}" vs "{Team B}" NBA win probability prediction model February 2026`
- **Key sources**: ESPN BPI game matchup pages, FiveThirtyEight-style ELO models
- **Note**: These are probability MODELS, not betting markets. Using them does NOT violate blind estimation.

---

## NCAA Basketball

### Team Ratings (KenPom / Barttorvik)
- **URL**: `https://barttorvik.com/` (more accessible than KenPom)
- **Tool**: `firecrawl_search`
- **Query**: `"{Team}" kenpom OR barttorvik 2026 efficiency ranking`
- **Schema** (if scraping Barttorvik):
  ```json
  {
    "type": "object",
    "properties": {
      "ranking": {"type": "number"},
      "adjusted_efficiency_margin": {"type": "number"},
      "offensive_efficiency": {"type": "number"},
      "defensive_efficiency": {"type": "number"},
      "record": {"type": "string"}
    }
  }
  ```

### Win Probability
- **Tool**: `firecrawl_search`
- **Query**: `"{Team A}" vs "{Team B}" college basketball prediction win probability 2026`
- **Key sources**: ESPN BPI college, TeamRankings.com, Haslametrics

### Injury Reports
- **Tool**: `firecrawl_search`
- **Query**: `"{Team}" college basketball injury report site:espn.com OR site:cbssports.com`

---

## Tennis (ATP / WTA)

### Player Stats & Rankings
- **ATP URL**: `https://www.atptour.com/en/players/{player-slug}/overview`
- **WTA URL**: `https://www.wtatennis.com/players/{player-id}/{player-slug}`
- **Tool**: `firecrawl_scrape` with JSON format
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "ranking": {"type": "number"},
      "ytd_win_loss": {"type": "string"},
      "surface_record_hard": {"type": "string"},
      "surface_record_clay": {"type": "string"},
      "surface_record_grass": {"type": "string"},
      "recent_results": {"type": "array", "items": {"type": "string"}}
    }
  }
  ```
- **Fallback query**: `"{Player}" ATP OR WTA ranking 2026 win loss record`

### Head-to-Head
- **Tool**: `firecrawl_search`
- **Query**: `"{Player A}" "{Player B}" head to head tennis record`
- **Key sources**: ATP Tour H2H page, Tennis Abstract

### Prediction Models (ELO-based)
- **Tool**: `firecrawl_search`
- **Query**: `"{Player A}" vs "{Player B}" tennis prediction ELO model 2026`
- **Key sources**: Tennis Abstract (ELO ratings), UltraTennis, OnCourt
- **Note**: ELO models are the best base rate source for tennis. They account for surface, recent form, and H2H.

### Injury / Withdrawal Watch
- **Tool**: `firecrawl_search`
- **Query**: `"{Player}" injury OR withdrawal OR retired tennis 2026`

---

## Soccer (Champions League, La Liga, Serie A, Premier League, Ligue 1)

### Team Form & Stats
- **URL**: `https://fbref.com/en/squads/{team_id}/{team_name}-Stats`
- **Tool**: `firecrawl_scrape` with JSON format
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "league_position": {"type": "number"},
      "points": {"type": "number"},
      "recent_form": {"type": "string"},
      "goals_for": {"type": "number"},
      "goals_against": {"type": "number"},
      "xG": {"type": "number"},
      "xGA": {"type": "number"},
      "home_record": {"type": "string"},
      "away_record": {"type": "string"}
    }
  }
  ```
- **Fallback query**: `"{Team}" 2025-26 season form stats xG site:fbref.com`

### Injuries & Squad News
- **Tool**: `firecrawl_search`
- **Query**: `"{Team}" injuries squad news site:transfermarkt.com OR site:espn.com`

### Win Probability / xG Models
- **Tool**: `firecrawl_search`
- **Query**: `"{Team A}" vs "{Team B}" prediction xG model win probability`
- **Key sources**: FBref xG data, Club ELO ratings, Opta-based models, Infogol
- **CRITICAL**: Soccer has THREE outcomes. Always find or estimate: P(home win), P(draw), P(away win). Typical draw rates:
  - Evenly matched league game: 25-30%
  - Mismatched (top vs bottom): 15-20%
  - UCL knockout first leg: 30-35%
  - UCL knockout second leg: 20-25%

### Head-to-Head
- **Tool**: `firecrawl_search`
- **Query**: `"{Team A}" vs "{Team B}" head to head history results`

---

## Economics

### GDP
- **Atlanta Fed GDPNow**: `https://www.atlantafed.org/cqer/research/gdpnow`
- **NY Fed Nowcast**: `https://www.newyorkfed.org/research/policy/nowcast`
- **Tool**: `firecrawl_scrape` with JSON format
- **Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "nowcast_estimate": {"type": "number"},
      "as_of_date": {"type": "string"},
      "prior_estimate": {"type": "number"}
    }
  }
  ```
- **Fallback query**: `Atlanta Fed GDPNow latest estimate 2026`

### CPI / Inflation
- **Cleveland Fed Nowcast**: `https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting`
- **BLS Latest Release**: `https://www.bls.gov/cpi/`
- **Tool**: `firecrawl_scrape` on Cleveland Fed page
- **Fallback query**: `CPI forecast consensus {month} 2026 inflation`

### Fed Rate
- **CME FedWatch**: `https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html`
- **Tool**: `firecrawl_scrape`
- **Note**: FedWatch probabilities are directly usable as base rates for Fed rate markets.
- **Fallback query**: `CME FedWatch tool Fed rate probability {month} 2026`

### Payrolls / Employment
- **Tool**: `firecrawl_search`
- **Query**: `nonfarm payrolls forecast consensus {month} 2026`
- **Key sources**: ADP National Employment Report, weekly jobless claims (BLS), ISM employment index

### Unemployment
- **Tool**: `firecrawl_search`
- **Query**: `unemployment rate forecast {month} 2026 consensus`

---

## General Search Templates

For any sport or market, these query templates provide structured context:

| Purpose | Tool | Query Template |
|---------|------|---------------|
| Injuries | `firecrawl_search` | `"{Team/Player}" injury report {date} site:espn.com OR site:cbssports.com` |
| Recent form | `firecrawl_search` | `"{Team/Player}" results last 10 games 2026` |
| H2H | `firecrawl_search` | `"{Team A}" vs "{Team B}" head to head history results` |
| Win probability model | `firecrawl_search` | `"{Team A}" vs "{Team B}" prediction win probability model -odds -betting` |
| Breaking news | `WebSearch` | `"{Team/Player}" news today {sport}` |
| Weather (outdoor) | `WebSearch` | `"{City}" weather {date} forecast` |
| Expert preview | `WebSearch` | `"{Team A}" vs "{Team B}" preview analysis {sport}` |

**Note**: Always add `-odds -betting -spread -moneyline` to model queries to filter out sportsbook content and focus on analytical models.
