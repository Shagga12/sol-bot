"""Deterministic, research-only spot strategy backtest.

Uses only past closing prices to choose the *next* interval's position.
No exchange credentials, network access, or order execution.
"""
from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from .quant_research import analyze_prices


@dataclass(frozen=True)
class BacktestResult:
    starting_usdt: float
    ending_usdt: float
    return_pct: float
    buy_and_hold_pct: float
    max_drawdown_pct: float
    trades: int
    fees_usdt: float
    execution_costs_usdt: float = 0.0


def backtest(prices: Sequence[float], starting_usdt: float = 1000.0,
             fee_rate: float = 0.001, fast: int = 10, slow: int = 30,
             max_volatility: float = 0.04, spread_rate: float = 0.0005,
             slippage_rate: float = 0.0005) -> BacktestResult:
    """Long-only close-to-next-close simulation with costs on every position change.

    Signals at close i apply to interval i->i+1, avoiding future-price leakage.
    Cash is assumed to earn zero. Spread and slippage are conservative fixed
    approximations charged on each entry/exit; latency is not modeled.
    Close-only candles cannot establish intrabar stop-loss/take-profit fills.
    """
    values = [float(p) for p in prices]
    if len(values) < slow + 2:
        raise ValueError("Insufficient prices for backtest")
    if any(not isfinite(p) or p <= 0 for p in values):
        raise ValueError("Prices must be positive and finite")
    if not isfinite(starting_usdt) or starting_usdt <= 0:
        raise ValueError("Starting balance must be positive")
    if not isfinite(fee_rate) or not 0 <= fee_rate < 1:
        raise ValueError("Invalid fee rate")
    if any(not isfinite(v) or not 0 <= v < 1 for v in (spread_rate, slippage_rate)):
        raise ValueError('Invalid execution cost assumption')
    equity = float(starting_usdt)
    peak = equity
    drawdown = 0.0
    position = 0
    trades = 0
    total_fees = 0.0
    total_execution_costs = 0.0
    for i in range(slow, len(values) - 1):
        signal = analyze_prices(values[:i + 1], fast, slow, max_volatility)
        target = (1 if signal.action == "BUY_CANDIDATE" else
                  0 if signal.action == "SELL_CANDIDATE" else position)
        if target != position:
            fee = equity * fee_rate
            equity -= fee
            total_fees += fee
            execution_cost = equity * (spread_rate / 2 + slippage_rate)
            equity -= execution_cost
            total_execution_costs += execution_cost
            trades += 1
            position = target
        if position:
            equity *= values[i + 1] / values[i]
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    # Mark final position to market without assuming liquidation.
    hold_return = (values[-1] / values[slow] - 1) * 100
    return BacktestResult(starting_usdt, equity,
                          (equity / starting_usdt - 1) * 100,
                          hold_return, drawdown * 100, trades, total_fees,
                          total_execution_costs)
