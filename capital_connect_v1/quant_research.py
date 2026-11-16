"""Research-only quantitative signal engine for Capital Connect.

This module never places orders, reads credentials, or enables live trading.
Signals are informational until independently backtested and approved.
"""
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Sequence


@dataclass(frozen=True)
class QuantSignal:
    action: str
    reason: str
    fast_average: float | None
    slow_average: float | None
    volatility: float | None
    confidence: float


def analyze_prices(prices: Sequence[float], fast: int = 10, slow: int = 30,
                   max_volatility: float = 0.04) -> QuantSignal:
    """Analyze consecutive equally spaced closing prices; no trade execution.

    Volatility is the population standard deviation of recent simple returns.
    A trend signal is withheld for invalid inputs, insufficient history,
    excessive volatility, or an ambiguous moving-average spread.
    """
    if fast < 2 or slow <= fast or not 0 < max_volatility < 1:
        raise ValueError("Invalid signal parameters")
    if len(prices) < slow + 1:
        return QuantSignal("WAIT", "insufficient_history", None, None, None, 0.0)
    values = [float(p) for p in prices]
    if any(not __import__("math").isfinite(p) or p <= 0 for p in values):
        return QuantSignal("WAIT", "invalid_prices", None, None, None, 0.0)
    recent = values[-(slow + 1):]
    returns = [b / a - 1 for a, b in zip(recent, recent[1:])]
    volatility = pstdev(returns)
    fast_avg = mean(values[-fast:])
    slow_avg = mean(values[-slow:])
    if volatility > max_volatility:
        return QuantSignal("WAIT", "volatility_limit", fast_avg, slow_avg, volatility, 0.0)
    spread = fast_avg / slow_avg - 1
    if abs(spread) < 0.002:
        return QuantSignal("WAIT", "no_clear_trend", fast_avg, slow_avg, volatility, 0.0)
    action = "BUY_CANDIDATE" if spread > 0 else "SELL_CANDIDATE"
    confidence = min(1.0, abs(spread) / 0.02)
    return QuantSignal(action, "moving_average_trend_research_only",
                       fast_avg, slow_avg, volatility, confidence)
