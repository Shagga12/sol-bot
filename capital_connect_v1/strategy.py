"""Deterministic, demo-only strategy with conservative sizing and risk checks."""
from dataclasses import dataclass
from decimal import Decimal

D = Decimal
MAX_TRADE_USDT = D("10")
MAX_ALLOCATION_PCT = D("0.10")
MAX_DAILY_LOSS_PCT = D("0.02")
MAX_SPREAD_PCT = D("0.003")
MIN_CANDLES = 30

@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    budget_usdt: Decimal = D("0")

def evaluate(closes, available_usdt, daily_realized_pnl_usdt, start_equity_usdt,
             spread_pct, has_open_position=False):
    """Inputs must come from verified market/account snapshots; no exchange writes."""
    values = [D(str(x)) for x in closes]
    cash = D(str(available_usdt))
    pnl = D(str(daily_realized_pnl_usdt))
    equity = D(str(start_equity_usdt))
    spread = D(str(spread_pct))
    if len(values) < MIN_CANDLES or any(not v.is_finite() or v <= 0 for v in values):
        return Decision("WAIT", "insufficient_or_invalid_market_data")
    if any(not v.is_finite() for v in (cash, pnl, equity, spread)) or cash < 0 or equity <= 0 or spread < 0:
        return Decision("WAIT", "invalid_account_or_spread_data")
    if pnl <= -(equity * MAX_DAILY_LOSS_PCT):
        return Decision("WAIT", "daily_loss_limit")
    if spread > MAX_SPREAD_PCT:
        return Decision("WAIT", "spread_too_wide")
    if has_open_position:
        return Decision("WAIT", "position_already_open")
    short_ma = sum(values[-10:]) / D(10)
    long_ma = sum(values[-30:]) / D(30)
    if short_ma <= long_ma:
        return Decision("WAIT", "no_buy_signal")
    budget = min(MAX_TRADE_USDT, cash * MAX_ALLOCATION_PCT)
    if budget <= 0:
        return Decision("WAIT", "no_available_balance")
    return Decision("DEMO_BUY", "moving_average_signal", budget)
