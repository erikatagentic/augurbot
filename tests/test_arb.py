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
from services.calculator import kalshi_fee, polymarket_fee


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

# ── fee model (the bug this whole correction fixed) ──

def test_polymarket_fee_is_price_proportional_not_flat():
    # The old bug charged a flat 0.02. Real taker is 0.30% of price.
    assert polymarket_fee(0.07, maker=False) == 0.003 * 0.07
    assert polymarket_fee(0.07) < 0.001          # nowhere near the old 0.02
    assert polymarket_fee(0.07, maker=True) == 0.0   # makers pay zero


def test_kalshi_maker_is_quarter_of_taker():
    assert kalshi_fee(0.5, maker=True) == 0.25 * kalshi_fee(0.5, maker=False)


# ── detector (maker/taker) ──

def test_detect_clear_arb_taker():
    # YES@kalshi 0.40 + NO@poly 0.40 = 0.80 -> ~0.18 edge net of real fees.
    r = detect_arb(
        kalshi_yes_bid=0.38, kalshi_yes_ask=0.40,
        poly_subject_bid=0.54, poly_subject_ask=0.55,
        poly_other_bid=0.39, poly_other_ask=0.40,
        mode="taker",
    )
    assert r["has_arb"] is True
    assert r["best_edge"] > 0.15
    assert r["direction"] == "YES@kalshi + NO@poly"


def test_detect_no_arb_efficient_taker():
    # Books sum to ~1.0 on both legs -> no taker edge.
    r = detect_arb(
        kalshi_yes_bid=0.49, kalshi_yes_ask=0.51,
        poly_subject_bid=0.49, poly_subject_ask=0.50,
        poly_other_bid=0.49, poly_other_ask=0.50,
        mode="taker",
    )
    assert r["has_arb"] is False
    assert r["best_edge"] <= 0.0


def test_detect_picks_mirror_leg_taker():
    # Subject cheap on Poly (ask 0.20), dear on Kalshi -> YES@poly + NO@kalshi.
    r = detect_arb(
        kalshi_yes_bid=0.68, kalshi_yes_ask=0.70,
        poly_subject_bid=0.19, poly_subject_ask=0.20,
        poly_other_bid=0.79, poly_other_ask=0.80,
        mode="taker",
    )
    assert r["has_arb"] is True
    assert r["direction"] == "YES@poly + NO@kalshi"


def test_maker_beats_taker_when_spreads_exist():
    # BTC-$120k-like snapshot: taker ~breakeven, maker clearly positive.
    common = dict(
        kalshi_yes_bid=0.08, kalshi_yes_ask=0.09,
        poly_subject_bid=0.06, poly_subject_ask=0.07,
        poly_other_bid=0.93, poly_other_ask=0.94,
    )
    taker = detect_arb(**common, mode="taker")
    maker = detect_arb(**common, mode="maker")
    assert maker["best_edge"] > taker["best_edge"]
    assert maker["mode"] == "maker"
