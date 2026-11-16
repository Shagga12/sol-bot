"""Offline Quant/attached-protection simulation. No account access or orders.

OHLC cannot prove fill availability. Assumptions must be supplied explicitly;
passing a simulation is never exchange validation or permission to trade.
"""
from dataclasses import dataclass
from decimal import Decimal as D
from .live import Config, floor, number
from .protection import attach_protection
from .quant_research import analyze_prices


@dataclass(frozen=True)
class Assumptions:
    fee: str
    exit_slippage: str
    tick: str
    quantity_step: str
    minimum_order: str

    def __post_init__(self):
        if not 0 <= number(self.fee) < D('.1'):
            raise ValueError('Invalid fee')
        if not 0 <= number(self.exit_slippage) < 1:
            raise ValueError('Invalid exit slippage')
        for field in ('tick', 'quantity_step', 'minimum_order'):
            number(getattr(self, field), True)


def simulate(candles, config: Config, assumptions: Assumptions):
    """31 past closes -> next open entry; one attached bracket at a time.

    Entry fills at its slippage ceiling, quote-denominated entry/exit fees.
    Gapped stops fill below the trigger. When both triggers touch, stop wins.
    The production attach_protection formula sets fee-adjusted rounded levels.
    The UTC daily realized-loss rule blocks entries, not protective exits.
    Four complete 15-minute buckets after every exit block reentry.
    Orders below the supplied minimum are skipped after quantity rounding.
    No SELL_CANDIDATE races an exchange-held bracket: exits use TP/SL only.
    """
    data = []
    previous = None
    for row in candles:
        raw = row['timestamp']
        ts = int(raw)
        if str(ts) != str(raw) or ts % 900 or (previous is not None and ts != previous + 900):
            raise ValueError('Consecutive aligned 15-minute candles required')
        o, h, l, c = (number(row[k], True) for k in ('open', 'high', 'low', 'close'))
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError('Inconsistent OHLC prices')
        data.append((ts, o, h, l, c)); previous = ts
    if len(data) < 33:
        raise ValueError('At least 33 candles required')
    cash = start = equity = number(config.capital_usdt)
    fee = number(assumptions.fee); slip = number(assumptions.exit_slippage)
    entry_slip = number(config.slippage_percent) / 100
    peak = start; drawdown = D(0); fees = D(0)
    position = None; last_exit = None; daily = {}; trades = []
    entries = daily_blocks = cooldown_blocks = minimum_blocks = 0
    rules = {'priceFilter': {'tickSize': assumptions.tick}}
    closes = [float(r[4]) for r in data]

    def mark(equity):
        nonlocal peak, drawdown
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)

    for i in range(31, len(data)):
        ts, opening, high, low, close = data[i]
        day = ts // 86400; bucket = ts // 900
        if position is None:
            if daily.get(day, D(0)) <= -number(config.daily_loss_usdt):
                daily_blocks += 1
            elif last_exit is not None and bucket - last_exit <= 4:
                cooldown_blocks += 1
            elif analyze_prices(closes[i-31:i]).action == 'BUY_CANDIDATE':
                budget = min(number(config.order_usdt), cash)
                price = floor(opening * (1 + entry_slip), assumptions.tick)
                if budget <= 0 or price < opening:
                    minimum_blocks += 1
                    continue
                qty = floor(budget / (price * (1 + fee)), assumptions.quantity_step)
                if qty <= 0 or qty * price < number(assumptions.minimum_order):
                    minimum_blocks += 1
                    continue
                bracket = attach_protection({'category': 'spot', 'side': 'Buy',
                    'orderType': 'Limit', 'price': str(price)}, config, rules, fee)
                value = qty * price; entry_fee = value * fee; cost = value + entry_fee
                assert cost <= budget <= number(config.order_usdt)
                cash -= cost; fees += entry_fee; entries += 1
                position = {'qty': qty, 'cost': cost, 'entry': ts,
                    'stop': D(bracket['stopLoss']), 'take': D(bracket['takeProfit'])}
        if position is not None:
            stop = position['stop']; take = position['take']
            exit_price = reason = None
            if opening <= stop:
                exit_price = opening * (1 - slip); reason = 'STOP_LOSS'
            elif opening >= take:
                exit_price = take * (1 - slip); reason = 'TAKE_PROFIT'
            elif low <= stop:
                exit_price = stop * (1 - slip); reason = 'STOP_LOSS'
            elif high >= take:
                exit_price = take * (1 - slip); reason = 'TAKE_PROFIT'
            if exit_price is not None:
                value = position['qty'] * exit_price; exit_fee = value * fee
                proceeds = value - exit_fee; pnl = proceeds - position['cost']
                cash += proceeds; fees += exit_fee
                daily[day] = daily.get(day, D(0)) + pnl
                trades.append({'entry': position['entry'], 'exit': ts, 'reason': reason,
                    'cost': str(position['cost']), 'pnl': str(pnl),
                    'stop': str(stop), 'take': str(take), 'exit_price': str(exit_price)})
                position = None; last_exit = bucket
            else:
                # Conservative mark at the bar's low, including estimated exit cost.
                mark(cash + position['qty'] * low * (1 - slip) * (1 - fee))
        equity = cash + (position['qty'] * close * (1 - slip) * (1 - fee) if position else D(0))
        mark(equity)
    return {'starting_quote': str(start), 'ending_liquidation_quote': str(equity),
        'net_return_pct': float((equity / start - 1) * 100),
        'max_drawdown_pct': float(drawdown * 100), 'entries': entries,
        'closed_trades': len(trades), 'wins': sum(D(t['pnl']) > 0 for t in trades),
        'fees_paid_quote': str(fees), 'daily_loss_blocks': daily_blocks,
        'cooldown_blocks': cooldown_blocks, 'minimum_order_blocks': minimum_blocks,
        'open_positions': int(position is not None), 'trades': trades,
        'exchange_validation': False, 'live_activation_approved': False}
