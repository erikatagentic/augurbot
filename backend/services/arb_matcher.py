"""Structured same-event matcher: Kalshi <-> Polymarket.

The June 2026 probe proved fuzzy token overlap produces ~50% false positives
(a single-match market colliding with a tournament-outright). This matcher is
structured instead:

  1. Parse the participant PAIR from each venue's title.
  2. Require both markets to be full-match-winner markets (reject Set/Map/
     Over-Under/score-first/tournament-outright).
  3. Match on the normalized participant set + resolution-date proximity.
  4. Align the Kalshi YES subject to the correct Polymarket outcome INDEX so
     the arb detector compares the price of the SAME outcome on both venues.

Scope: head-to-head sports (the proven overlap, currently tennis). Extensible
to other H2H markets; deliberately conservative — better to miss a pair than
to mismatch one and fire a bad arb.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Qualifiers that mean a market is NOT a full-match-winner.
_DISQUALIFIERS = (
    "set ", "set1", "1st set", "2nd set", "game ", "o/u", "over/under",
    "over under", " map ", "map ", "to score", "first to", "winner:",
    "period", "half", "quarter", " leg ", "correct score", "handicap",
    "spread", "total", "props", "mvp", "to win the 20", "champion",
    "winner of the", "tournament", "outright",
)

# Tournament/league prefixes to strip from Polymarket titles before the split.
_PREFIX_RE = re.compile(
    r"^(wimbledon\s+(atp|wta)|atp|wta|milan|us open|french open|"
    r"australian open|nba|nfl|mlb|nhl|ucl|epl|laliga|serie a|"
    r"counter-strike|cs2?|valorant|lol)\s*[:\-]\s*",
    re.IGNORECASE,
)

_VS_RE = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)
_KALSHI_SUBJECT_RE = re.compile(r"will\s+(.+?)\s+win\s+the\s+", re.IGNORECASE)


@dataclass
class ArbPair:
    """A confirmed cross-venue match on the same binary outcome."""

    kalshi_ticker: str
    kalshi_question: str
    kalshi_subject: str            # the player the Kalshi YES resolves on
    poly_question: str
    poly_condition_id: str
    poly_subject_index: int        # outcome index on Poly == kalshi_subject
    poly_token_ids: list[str]
    participants: tuple[str, str]
    end_date: str
    confidence: float

    def key(self) -> str:
        return f"{self.kalshi_ticker}|{self.poly_condition_id}"


# ── name normalization ──

def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def norm_tokens(name: str) -> set[str]:
    """Normalized significant tokens of a participant name.

    Lowercased, accent- and hyphen-stripped, punctuation removed. 'Soon-Woo
    Kwon' and 'Soonwoo Kwon' both -> {'soonwoo', 'kwon'} ... close enough:
    hyphens are removed so 'soon', 'woo' merge to 'soonwoo' only if adjacent.
    We additionally fold internal hyphens, so 'soon-woo' -> 'soonwoo'.
    """
    s = strip_accents(name).lower()
    s = s.replace("-", "")               # soon-woo -> soonwoo
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return {t for t in s.split() if len(t) > 1}


def last_name(name: str) -> str:
    toks = [t for t in norm_tokens(name)]
    # heuristic: the longest token is usually the surname; fall back to last
    raw = strip_accents(name).lower().replace("-", "")
    raw = re.sub(r"[^a-z0-9 ]", " ", raw).split()
    return raw[-1] if raw else ""


# ── market-type gate ──

def is_full_match_market(text: str) -> bool:
    """True if the title looks like a full head-to-head match-winner market."""
    t = text.lower()
    return not any(q in t for q in _DISQUALIFIERS)


# ── parsers ──

def parse_kalshi_h2h(market: dict) -> tuple[str, frozenset[str]] | None:
    """Return (subject_name, {participant_a, participant_b}) or None.

    Uses the normalized `outcome_label` as the subject when present, else
    parses 'Will X win the A vs B ...'. Requires an 'A vs B' pair and a
    full-match market.
    """
    q = market.get("question", "") or ""
    if "match" not in q.lower() or not is_full_match_market(q):
        return None

    # participant pair from 'A vs B:' inside the question
    m = re.search(r"the\s+(.+?)\s+vs\.?\s+(.+?)[:?]", q, re.IGNORECASE)
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()

    subject = (market.get("outcome_label") or "").strip()
    if not subject:
        sm = _KALSHI_SUBJECT_RE.search(q)
        if not sm:
            return None
        subject = sm.group(1).strip()

    return subject, frozenset({last_name(a), last_name(b)})


def parse_poly_h2h(market: dict) -> tuple[list[str], frozenset[str]] | None:
    """Return (outcome_labels, {participant_a, participant_b}) or None.

    Polymarket H2H markets carry player-name outcomes aligned by index with
    outcomePrices and clobTokenIds. Reject Yes/No-structured and non-match
    markets.
    """
    q = market.get("question", "") or market.get("title", "") or ""
    if not is_full_match_market(q):
        return None

    outcomes = market.get("outcomes")
    if isinstance(outcomes, str):
        try:
            import json
            outcomes = json.loads(outcomes)
        except (ValueError, TypeError):
            return None
    if not isinstance(outcomes, list) or len(outcomes) != 2:
        return None
    if any(str(o).strip().lower() in ("yes", "no") for o in outcomes):
        return None  # Yes/No prop, not a two-player H2H

    body = _PREFIX_RE.sub("", q)
    parts = _VS_RE.split(body)
    if len(parts) != 2:
        # fall back to the outcome labels as the pair
        a, b = outcomes[0], outcomes[1]
    else:
        a, b = parts[0], parts[1]

    return list(outcomes), frozenset({last_name(a), last_name(b)})


# ── date helper ──

def _date_str(s: str | None) -> str:
    return (s or "")[:10]


def _days_apart(d1: str, d2: str) -> int | None:
    """Absolute day difference between two ISO date strings, or None if either
    is unparseable. Cross-venue dates are noisy (Kalshi match-date vs Poly
    resolution-deadline), so this drives a graded confidence, not a hard cut
    inside the window."""
    from datetime import date
    try:
        y1, m1, day1 = (int(x) for x in d1[:10].split("-"))
        y2, m2, day2 = (int(x) for x in d2[:10].split("-"))
        return abs((date(y1, m1, day1) - date(y2, m2, day2)).days)
    except (ValueError, AttributeError):
        return None


# ── the matcher ──

def match_markets(
    kalshi_markets: list[dict],
    poly_markets: list[dict],
    max_days: int = 14,
) -> list[ArbPair]:
    """Return structured same-event pairs with subject alignment."""
    poly_parsed = []
    for pm in poly_markets:
        parsed = parse_poly_h2h(pm)
        if parsed:
            poly_parsed.append((pm, parsed[0], parsed[1]))

    pairs: list[ArbPair] = []
    for km in kalshi_markets:
        kp = parse_kalshi_h2h(km)
        if not kp:
            continue
        subject, k_pair = kp
        subject_ln = last_name(subject)
        k_date = _date_str(km.get("game_date") or km.get("close_date"))

        for pm, outcomes, p_pair in poly_parsed:
            if k_pair != p_pair:
                continue
            p_date = _date_str(pm.get("endDate") or pm.get("end_date"))
            dd = _days_apart(k_date, p_date) if (k_date and p_date) else None
            if dd is not None and dd > max_days:
                continue

            # align subject to a Polymarket outcome index
            subj_idx = None
            for i, label in enumerate(outcomes):
                if last_name(label) == subject_ln:
                    subj_idx = i
                    break
            if subj_idx is None:
                continue

            token_ids = pm.get("clobTokenIds")
            if isinstance(token_ids, str):
                try:
                    import json
                    token_ids = json.loads(token_ids)
                except (ValueError, TypeError):
                    token_ids = []

            if dd is None:
                confidence = 0.6        # no date corroboration
            elif dd <= 3:
                confidence = 1.0        # dates agree closely
            else:
                confidence = 0.75       # same participants, looser date match
            pairs.append(ArbPair(
                kalshi_ticker=km.get("ticker") or km.get("platform_id", ""),
                kalshi_question=km.get("question", ""),
                kalshi_subject=subject,
                poly_question=pm.get("question", ""),
                poly_condition_id=pm.get("conditionId", ""),
                poly_subject_index=subj_idx,
                poly_token_ids=token_ids or [],
                participants=tuple(sorted(k_pair)),
                end_date=p_date or k_date,
                confidence=confidence,
            ))
    return pairs
