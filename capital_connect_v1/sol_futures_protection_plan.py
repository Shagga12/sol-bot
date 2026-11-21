"""Pure SOLUSDT Futures protection plan for Capital Connect.

No API calls or order placement. Values describe SOL price movement, not
leveraged account ROI. Exchange tick-size rounding and minimum order sizes
must be validated against Bybit instruments info before submission.
"""
from decimal import Decimal, ROUND_DOWN, ROUND_UP

D = lambda value: Decimal(str(value))

def protection_plan(entry_price, side, stop_pct="0.01", take_pct="0.04",
                    activation_pct="0.02", trailing_pct="0.01", tick="0.001"):
    entry, step = D(entry_price), D(tick)
    if entry <= 0 or step <= 0:
        raise ValueError("entry and tick must be positive")
    if side not in ("Buy", "Sell"):
        raise ValueError("side must be Buy or Sell")
    sl, tp, activation, trail = map(D, (stop_pct, take_pct, activation_pct, trailing_pct))
    if not (0 < sl < 1 and 0 < tp < 1 and 0 < activation < 1 and 0 < trail < 1):
        raise ValueError("percentages must be between zero and one")
    long = side == "Buy"
    def rounded(price, mode):
        return (price / step).to_integral_value(rounding=mode) * step
    stop = rounded(entry * (1 - sl if long else 1 + sl), ROUND_DOWN if long else ROUND_UP)
    take = rounded(entry * (1 + tp if long else 1 - tp), ROUND_UP if long else ROUND_DOWN)
    active = rounded(entry * (1 + activation if long else 1 - activation), ROUND_UP if long else ROUND_DOWN)
    distance = rounded(entry * trail, ROUND_UP)
    if distance <= 0:
        raise ValueError("trailing distance below tick")
    return {
        "symbol": "SOLUSDT", "category": "linear", "side": side,
        "stop_loss": str(stop), "take_profit": str(take),
        "trailing_activation_price": str(active),
        "trailing_distance_usdt": str(distance),
        "requires_exchange_confirmation": True,
        "live_orders_enabled": False,
    }
