"""Deterministic pre-trade risk checks.

Guide Step 4 hardening: risk validation lives in code, not in markdown the
model re-interprets. `tools/bet.py` gathers live inputs (balance, open bets,
bankroll history, live order book) and calls `pre_trade_check()` before EVERY
order. Pure logic + filesystem kill-switch check, so it's unit-testable with
plain dicts.

Defaults mirror backend/config.py; bet.py overrides them from settings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

KILL_SWITCH_FILENAME = "STOP"


@dataclass
class RiskResult:
    """Outcome of a pre-trade check. `allowed` is False if any hard block fired."""

    allowed: bool
    reasons: list[str] = field(default_factory=list)   # hard blocks
    warnings: list[str] = field(default_factory=list)   # non-blocking notes
    kill_switch: bool = False                            # absolute, non-overridable

    def render(self) -> str:
        lines: list[str] = []
        if self.allowed:
            lines.append("  RISK CHECK: PASS")
        else:
            lines.append("  RISK CHECK: BLOCKED")
        for r in self.reasons:
            lines.append(f"    [BLOCK] {r}")
        for w in self.warnings:
            lines.append(f"    [warn]  {w}")
        return "\n".join(lines)


# ── Kill switch ──

def kill_switch_active(repo_root: str | Path) -> bool:
    """True if a STOP file exists at the repo root. Absolute halt."""
    return (Path(repo_root) / KILL_SWITCH_FILENAME).exists()


# ── Portfolio state helpers (operate on data/bets.json records) ──

def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def open_bets(bets: list[dict]) -> list[dict]:
    return [b for b in bets if b.get("status") == "open"]


def open_exposure(bets: list[dict]) -> float:
    """Total dollars deployed in open positions (sum of entry cost)."""
    return sum(float(b.get("cost") or 0.0) for b in open_bets(bets))


def event_key(ticker: str) -> str:
    """Kalshi tickers are SERIES-EVENT-OUTCOME; the event is the first two
    segments. Used to cap exposure to a single game/event."""
    parts = (ticker or "").split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else (ticker or "")


def event_exposure(bets: list[dict], ticker: str) -> float:
    ek = event_key(ticker)
    return sum(
        float(b.get("cost") or 0.0)
        for b in open_bets(bets)
        if event_key(b.get("ticker", "")) == ek
    )


def daily_realized_pnl(bets: list[dict], today: date) -> float:
    """Sum of realized P&L on bets that closed today (UTC date)."""
    total = 0.0
    for b in bets:
        if b.get("pnl") is None:
            continue
        closed = _parse_dt(b.get("closed_at"))
        if closed and closed.date() == today:
            total += float(b.get("pnl") or 0.0)
    return total


def max_drawdown_pct(bankroll_history: list[dict]) -> float:
    """Peak-to-trough drawdown over the bankroll snapshot history, as a
    fraction (0.08 == 8%). Uses kalshi_total."""
    vals = [
        float(h.get("kalshi_total") or 0.0)
        for h in bankroll_history
        if h.get("kalshi_total") is not None
    ]
    if len(vals) < 2:
        return 0.0
    peak = vals[0]
    mdd = 0.0
    for v in vals:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def entry_cost(side: str, count: int, yes_price_cents: float) -> float:
    """Dollars to enter `count` contracts. YES pays the YES price; NO pays
    (100 - YES price)."""
    if side == "yes":
        return count * yes_price_cents / 100.0
    return count * (100 - yes_price_cents) / 100.0


def _live_entry_cost_per_contract(side: str, live_book: dict) -> float | None:
    """Executable entry cost per contract (dollars) from the live book.
    YES pays the ask; NO pays (100 - yes_bid)."""
    if side == "yes":
        ask = live_book.get("yes_ask")
        return None if ask is None else float(ask) / 100.0
    bid = live_book.get("yes_bid")
    return None if bid is None else (100 - float(bid)) / 100.0


# ── The gate ──

def pre_trade_check(
    *,
    repo_root: str | Path,
    ticker: str,
    side: str,
    count: int,
    intended_yes_price: float,
    cash: float,
    total: float,
    bets: list[dict],
    bankroll_history: list[dict],
    live_book: dict | None,
    daily_loss_limit_fraction: float = 0.15,
    max_drawdown_halt_fraction: float = 0.08,
    max_open_positions: int = 10,
    max_exposure_fraction: float = 0.25,
    max_event_exposure_fraction: float = 0.10,
    max_single_bet_fraction: float = 0.03,
    slippage_tolerance: float = 0.05,
    max_spread_cents: float = 10.0,
    today: date | None = None,
) -> RiskResult:
    """Run every hard gate. Returns a RiskResult; `allowed` is False if any
    block fired. The kill switch is flagged separately so callers can treat it
    as non-overridable.

    `cash`   = live withdrawable cash (dollars) — used for affordability.
    `total`  = total account value cash+portfolio (dollars) — base for caps.
    `live_book` = {"yes_bid": cents, "yes_ask": cents} fetched at order time.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    # 0. Kill switch — absolute.
    ks = kill_switch_active(repo_root)
    if ks:
        reasons.append("Kill switch active (STOP file present at repo root)")

    cost = entry_cost(side, count, intended_yes_price)

    # 1. Affordability.
    if cost > cash:
        reasons.append(f"Insufficient cash: cost ${cost:.2f} > cash ${cash:.2f}")

    # 2. Single-bet cap.
    single_cap = total * max_single_bet_fraction
    if cost > single_cap:
        reasons.append(
            f"Bet ${cost:.2f} exceeds single-bet cap ${single_cap:.2f} "
            f"({max_single_bet_fraction:.0%} of ${total:.2f})"
        )

    # 3. Daily loss limit.
    if today is not None:
        day_pnl = daily_realized_pnl(bets, today)
        loss_limit = -daily_loss_limit_fraction * total
        if day_pnl <= loss_limit:
            reasons.append(
                f"Daily loss ${day_pnl:.2f} hit limit ${loss_limit:.2f} "
                f"({daily_loss_limit_fraction:.0%}) — trading halted today"
            )

    # 4. Max drawdown halt.
    mdd = max_drawdown_pct(bankroll_history)
    if mdd >= max_drawdown_halt_fraction:
        reasons.append(
            f"Drawdown {mdd:.1%} >= halt threshold "
            f"{max_drawdown_halt_fraction:.0%}"
        )

    # 5. Max concurrent positions.
    n_open = len(open_bets(bets))
    if n_open >= max_open_positions:
        reasons.append(
            f"Open positions {n_open} >= cap {max_open_positions}"
        )

    # 6. Total portfolio exposure.
    exp = open_exposure(bets)
    exp_cap = total * max_exposure_fraction
    if exp + cost > exp_cap:
        reasons.append(
            f"Exposure ${exp + cost:.2f} (open ${exp:.2f} + bet ${cost:.2f}) "
            f"exceeds cap ${exp_cap:.2f} ({max_exposure_fraction:.0%})"
        )

    # 7. Per-event exposure.
    ev_exp = event_exposure(bets, ticker)
    ev_cap = total * max_event_exposure_fraction
    if ev_exp + cost > ev_cap:
        reasons.append(
            f"Event exposure ${ev_exp + cost:.2f} exceeds per-event cap "
            f"${ev_cap:.2f} ({max_event_exposure_fraction:.0%})"
        )

    # 8. Slippage + spread recheck (needs a live book).
    if live_book is None:
        reasons.append("No live order book — cannot verify executable price")
    else:
        bid = live_book.get("yes_bid")
        ask = live_book.get("yes_ask")
        if bid is None or ask is None:
            reasons.append("Live book missing bid/ask — cannot verify price")
        else:
            spread = float(ask) - float(bid)
            if spread > max_spread_cents:
                reasons.append(
                    f"Spread {spread:.0f}c > max {max_spread_cents:.0f}c "
                    f"(illiquid)"
                )
            intended = entry_cost(side, 1, intended_yes_price)
            live = _live_entry_cost_per_contract(side, live_book)
            if live is not None and intended > 0:
                slip = (live - intended) / intended
                if slip > slippage_tolerance:
                    reasons.append(
                        f"Price moved against us {slip:.1%} "
                        f"(intended ${intended:.2f}/contract, "
                        f"live ${live:.2f}) > tol {slippage_tolerance:.0%}"
                    )
                elif slip < -slippage_tolerance:
                    warnings.append(
                        f"Price moved in our favor {abs(slip):.1%} "
                        f"(live cheaper than intended)"
                    )

    return RiskResult(
        allowed=len(reasons) == 0,
        reasons=reasons,
        warnings=warnings,
        kill_switch=ks,
    )
