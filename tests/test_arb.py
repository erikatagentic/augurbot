"""Tests for the cross-venue arbitrage matcher + detector.

Examples are taken verbatim from the June 2026 live overlap probe.
"""
from services.arb_matcher import (
    is_full_match_market,
    last_name,
    match_markets,
    norm_tokens,
    parse_kalshi_h2h,
    parse_poly_h2h,
)
from services.arb_detector import detect_arb


# ── Fixtures from the live probe ──

KALSHI_NAVONE = {
    "ticker": "KXTENNISMATCH-26JUL06NAVCOB-NAV",
    "platform_id": "KXTENNISMATCH-26JUL06NAVCOB-NAV",
    "question": "Will Mariano Navone win the Navone vs Cobolli: Round Of 128 match?",
    "outcome_label": "Mariano Navone",
    "close_date": "2026-07-06T12:00:00Z",
    "game_date": "2026-07-06T12:00:00Z",
    "yes_bid": 0.22,
    "yes_ask": 0.26,
}

POLY_NAVONE = {
    "question": "Wimbledon ATP: Mariano Navone vs Flavio Cobolli",
    "outcomes": ["Mariano Navone", "Flavio Cobolli"],
    "outcomePrices": ["0.245", "0.755"],
    "clobTokenIds": ["tok_navone", "tok_cobolli"],
    "conditionId": "0xabc",
    "endDate": "2026-07-06T14:00:00Z",
}

# A tournament-outright that token-collides but must NOT match a single match.
POLY_FONSECA_OUTRIGHT = {
    "question": "Will Joao Fonseca win the 2026 Men's US Open?",
    "outcomes": ["Yes", "No"],
    "outcomePrices": ["0.08", "0.92"],
    "clobTokenIds": ["t1", "t2"],
    "conditionId": "0xdef",
    "endDate": "2026-09-01T00:00:00Z",
}


# ── normalization ──

def test_norm_handles_hyphen_and_accent():
    assert norm_tokens("Soon-Woo Kwon") == norm_tokens("Soonwoo Kwon")
    assert "navone" in norm_tokens("Mariano Navoné")


def test_last_name():
    assert last_name("Mariano Navone") == "navone"
    assert last_name("Flavio Cobolli") == "cobolli"


# ── market-type gate ──

def test_full_match_gate():
    assert is_full_match_market("Wimbledon ATP: Navone vs Cobolli") is True
    assert is_full_match_market("Set 1 Winner: Mayot vs Nedic") is False
    assert is_full_match_market("Germany vs. Paraguay: O/U 3.5") is False
    assert is_full_match_market("Counter-Strike: BIG vs Kinoa - Map 2 Winner") is False
    # Pure outrights (no 'vs') are rejected by the parsers, not this gate; but
    # an explicit 'to win ... outright' phrasing is screened here too.
    assert is_full_match_market("Alcaraz to win the 2026 US Open outright") is False


# ── parsers ──

def test_parse_kalshi():
    out = parse_kalshi_h2h(KALSHI_NAVONE)
    assert out is not None
    subject, pair = out
    assert subject == "Mariano Navone"
    assert pair == frozenset({"navone", "cobolli"})


def test_parse_poly():
    out = parse_poly_h2h(POLY_NAVONE)
    assert out is not None
    outcomes, pair = out
    assert outcomes == ["Mariano Navone", "Flavio Cobolli"]
    assert pair == frozenset({"navone", "cobolli"})


def test_parse_poly_rejects_yesno_outright():
    assert parse_poly_h2h(POLY_FONSECA_OUTRIGHT) is None


# ── matcher ──

def test_match_aligns_subject_index():
    pairs = match_markets([KALSHI_NAVONE], [POLY_NAVONE, POLY_FONSECA_OUTRIGHT])
    assert len(pairs) == 1
    p = pairs[0]
    assert p.kalshi_subject == "Mariano Navone"
    assert p.poly_subject_index == 0          # Navone is outcome[0] on Poly
    assert p.poly_token_ids[p.poly_subject_index] == "tok_navone"
    assert p.participants == ("cobolli", "navone")
    assert p.confidence == 1.0


def test_match_rejects_outright_only():
    # Only the outright Poly market present -> no valid match.
    pairs = match_markets([KALSHI_NAVONE], [POLY_FONSECA_OUTRIGHT])
    assert pairs == []


def test_match_respects_date_window():
    far = {**POLY_NAVONE, "endDate": "2026-08-20T00:00:00Z"}
    pairs = match_markets([KALSHI_NAVONE], [far], max_days=3)
    assert pairs == []


# ── detector ──

def test_detect_clear_arb():
    # YES_S 0.40 on Kalshi + NO_S 0.40 on Poly = 0.80 cost -> ~0.18 edge net.
    r = detect_arb(
        kalshi_yes_ask=0.40, kalshi_yes_bid=0.38,
        poly_subject_price=0.55, poly_other_price=0.40,
    )
    assert r["has_arb"] is True
    assert r["best_edge"] > 0.15
    assert r["legs"]["buy_yes_on"] == "kalshi"


def test_detect_no_arb_efficient():
    # Prices agree (~0.50 each side) -> combined cost ~1.0 -> no edge.
    r = detect_arb(
        kalshi_yes_ask=0.51, kalshi_yes_bid=0.49,
        poly_subject_price=0.50, poly_other_price=0.50,
    )
    assert r["has_arb"] is False
    assert r["best_edge"] <= 0.0


def test_detect_picks_mirror_leg():
    # Subject cheap on Poly (0.20), expensive on Kalshi (ask 0.70):
    # buy YES on Poly + NO on Kalshi (1-0.68=0.32) -> 0.52 cost -> big edge.
    r = detect_arb(
        kalshi_yes_ask=0.70, kalshi_yes_bid=0.68,
        poly_subject_price=0.20, poly_other_price=0.80,
    )
    assert r["has_arb"] is True
    assert r["legs"]["buy_yes_on"] == "polymarket"
