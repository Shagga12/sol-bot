"""Conservative, deterministic SOLUSDT Futures direction proposal.

Signals are advisory only: no exchange requests, orders or automatic activation.
Requires closed candles, a fast/slow trend and a minimum separation to avoid
trading on a weak/ambiguous trend. No profitability claim is implied.
"""
from decimal import Decimal, InvalidOperation

class SignalError(ValueError):
    pass

def _price(value):
    try:
        p = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise SignalError("Invalid candle close") from None
    if not p.is_finite() or p <= 0:
        raise SignalError("Candle closes must be finite and positive")
    return p

def propose_direction(closed_candle_prices, *, min_separation="0.002"):
    """Return LONG, SHORT or WAIT, never a live trading instruction.

    Uses the mean of the last 5 and 20 completed candle closes. The latest
    candle must agree with the trend. No hedging, no multiple positions.
    """
    if not isinstance(closed_candle_prices, (list, tuple)) or len(closed_candle_prices) < 20:
        raise SignalError("At least 20 completed candles are required")
    prices = [_price(x) for x in closed_candle_prices]
    try:
        threshold = Decimal(str(min_separation))
    except (InvalidOperation, ValueError, TypeError):
        raise SignalError("Invalid threshold") from None
    if not threshold.is_finite() or threshold < Decimal("0.002") or threshold > Decimal("0.02"):
        raise SignalError("Trend threshold outside safety range")
    fast = sum(prices[-5:]) / 5
    slow = sum(prices[-20:]) / 20
    relative_gap = (fast - slow) / slow
    if relative_gap >= threshold and prices[-1] > fast:
        return "LONG"
    if relative_gap <= -threshold and prices[-1] < fast:
        return "SHORT"
    return "WAIT"

def proposed_protection(entry_price, direction):
    """Calculate raw price targets; exchange tick rounding must be done later."""
    entry = _price(entry_price)
    if direction == "LONG":
        return {"stop_loss": str(entry * Decimal("0.99")),
                "take_profit": str(entry * Decimal("1.04"))}
    if direction == "SHORT":
        return {"stop_loss": str(entry * Decimal("1.01")),
                "take_profit": str(entry * Decimal("0.96"))}
    raise SignalError("Only LONG or SHORT may have protective targets")
