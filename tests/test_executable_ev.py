from services.calculator import calculate_ev


def test_yes_edge_measured_against_ask_not_mid():
    # AI says 0.60. last/mid = 0.50 (looks like +0.10 edge) but ask = 0.57.
    r = calculate_ev(0.60, 0.50, "kalshi", yes_ask=0.57, yes_bid=0.53)
    assert r is not None
    assert r["direction"] == "yes"
    assert abs(r["edge"] - 0.03) < 1e-6  # 0.60 - 0.57, not 0.60 - 0.50


def test_no_edge_measured_against_bid():
    # AI says 0.40 (YES). Market mid 0.50, bid 0.47, ask 0.53.
    # NO edge = yes_bid - ai_prob = 0.47 - 0.40 = 0.07.
    r = calculate_ev(0.40, 0.50, "kalshi", yes_ask=0.53, yes_bid=0.47)
    assert r is not None
    assert r["direction"] == "no"
    assert abs(r["edge"] - 0.07) < 1e-6


def test_phantom_edge_disappears_against_ask():
    # AI 0.55, mid 0.50 -> looks like +0.05 YES edge, but ask 0.56 kills it.
    r = calculate_ev(0.55, 0.50, "kalshi", yes_ask=0.56, yes_bid=0.44)
    # YES edge negative (0.55-0.56), NO edge negative (0.44-0.55) -> no bet.
    assert r is None


def test_backward_compatible_when_no_executable_prices():
    # Omitting yes_ask/yes_bid must reproduce the old single-price behavior.
    assert calculate_ev(0.60, 0.50, "kalshi") == calculate_ev(
        0.60, 0.50, "kalshi", yes_ask=0.50, yes_bid=0.50
    )
