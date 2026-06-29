"""Unit tests for the deterministic pre-trade risk guard."""
from datetime import date

from services.risk_guard import (
    RiskResult,
    daily_realized_pnl,
    event_exposure,
    event_key,
    kill_switch_active,
    max_drawdown_pct,
    open_exposure,
    pre_trade_check,
)

# A healthy account that should pass an ordinary small bet.
HEALTHY = dict(
    repo_root="/nonexistent-repo-root",  # no STOP file there
    ticker="KXNBAGAME-26FEB19DETNYK-DET",
    side="yes",
    count=5,
    intended_yes_price=40,            # 5 contracts @ 40c -> $2.00 cost
    cash=150.0,
    total=160.0,
    bets=[],
    bankroll_history=[],
    live_book={"yes_bid": 39, "yes_ask": 41},  # 2c spread, on-price
    today=date(2026, 6, 29),
)


def _run(**overrides):
    args = {**HEALTHY, **overrides}
    return pre_trade_check(**args)


def test_healthy_bet_passes():
    r = _run()
    assert isinstance(r, RiskResult)
    assert r.allowed is True, r.reasons
    assert r.reasons == []


def test_kill_switch_blocks(tmp_path):
    (tmp_path / "STOP").write_text("halt")
    assert kill_switch_active(tmp_path) is True
    r = _run(repo_root=tmp_path)
    assert r.allowed is False
    assert r.kill_switch is True
    assert any("Kill switch" in x for x in r.reasons)


def test_no_stop_file_not_active(tmp_path):
    assert kill_switch_active(tmp_path) is False


def test_insufficient_cash_blocks():
    r = _run(cash=1.0)  # $2 bet > $1 cash
    assert r.allowed is False
    assert any("Insufficient cash" in x for x in r.reasons)


def test_single_bet_cap_blocks():
    # 50 contracts @ 40c = $20 on a $160 account; 3% cap = $4.80.
    r = _run(count=50)
    assert r.allowed is False
    assert any("single-bet cap" in x for x in r.reasons)


def test_daily_loss_limit_blocks():
    # Closed today at -$30 on a $160 account; 15% limit = -$24.
    bets = [
        {"status": "closed", "pnl": -30.0, "closed_at": "2026-06-29T12:00:00Z"},
    ]
    r = _run(bets=bets)
    assert r.allowed is False
    assert any("Daily loss" in x for x in r.reasons)


def test_daily_loss_ignores_other_days():
    bets = [
        {"status": "closed", "pnl": -30.0, "closed_at": "2026-06-28T12:00:00Z"},
    ]
    r = _run(bets=bets)
    assert r.allowed is True, r.reasons


def test_drawdown_halt_blocks():
    # Peak 200 -> trough 170 = 15% drawdown; halt at 8%.
    hist = [
        {"kalshi_total": 200.0},
        {"kalshi_total": 185.0},
        {"kalshi_total": 170.0},
    ]
    r = _run(bankroll_history=hist)
    assert r.allowed is False
    assert any("Drawdown" in x for x in r.reasons)


def test_max_positions_blocks():
    bets = [
        {"status": "open", "cost": 1.0, "ticker": f"T{i}-E{i}-O"}
        for i in range(10)
    ]
    r = _run(bets=bets)
    assert r.allowed is False
    assert any("Open positions" in x for x in r.reasons)


def test_total_exposure_blocks():
    # $40 already open on a $160 account; 25% cap = $40, +$2 bet -> over.
    bets = [{"status": "open", "cost": 40.0, "ticker": "OTHER-EVT-O"}]
    r = _run(bets=bets)
    assert r.allowed is False
    assert any("Exposure" in x for x in r.reasons)


def test_event_exposure_blocks():
    # $15 already open on the SAME event; per-event cap 10% = $16, +$2 -> over.
    bets = [
        {"status": "open", "cost": 15.0,
         "ticker": "KXNBAGAME-26FEB19DETNYK-NYK"},
    ]
    r = _run(bets=bets)
    assert r.allowed is False
    assert any("Event exposure" in x for x in r.reasons)


def test_wide_spread_blocks():
    r = _run(live_book={"yes_bid": 30, "yes_ask": 55})  # 25c spread
    assert r.allowed is False
    assert any("Spread" in x for x in r.reasons)


def test_slippage_against_us_blocks():
    # Intended 40c, live ask 50c -> 25% slippage > 5% tol.
    r = _run(intended_yes_price=40, live_book={"yes_bid": 48, "yes_ask": 50})
    assert r.allowed is False
    assert any("moved against us" in x for x in r.reasons)


def test_slippage_in_favor_warns_not_blocks():
    # Intended 40c, live ask 36c -> price cheaper, allowed with a warning.
    r = _run(intended_yes_price=40, live_book={"yes_bid": 35, "yes_ask": 36})
    assert r.allowed is True, r.reasons
    assert any("favor" in w for w in r.warnings)


def test_missing_book_blocks():
    r = _run(live_book=None)
    assert r.allowed is False
    assert any("No live order book" in x for x in r.reasons)


def test_no_side_no_bet_cost_helpers():
    # NO entry cost: 5 contracts at YES-price 40 -> pays (100-40)=60c -> $3.00
    from services.risk_guard import entry_cost
    assert entry_cost("no", 5, 40) == 3.0
    assert entry_cost("yes", 5, 40) == 2.0


def test_event_key_parsing():
    assert event_key("KXNBAGAME-26FEB19DETNYK-DET") == "KXNBAGAME-26FEB19DETNYK"
    assert event_key("SINGLE") == "SINGLE"


def test_helper_aggregations():
    bets = [
        {"status": "open", "cost": 5.0, "ticker": "A-E1-X"},
        {"status": "open", "cost": 3.0, "ticker": "A-E1-Y"},
        {"status": "closed", "cost": 9.0, "ticker": "A-E1-Z"},
    ]
    assert open_exposure(bets) == 8.0
    assert event_exposure(bets, "A-E1-Q") == 8.0
    assert daily_realized_pnl(
        [{"pnl": -2.0, "closed_at": "2026-06-29T01:00:00Z"}], date(2026, 6, 29)
    ) == -2.0
    assert max_drawdown_pct([{"kalshi_total": 100}, {"kalshi_total": 75}]) == 0.25
