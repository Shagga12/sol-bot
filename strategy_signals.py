"""Pure decision logic for strategy review. Simulation only; no exchange imports.

Produces informational signals, never payloads or execution authorization. The
illustrative parameters are unbacktested, unapproved and not a profit forecast.
"""
from decimal import Decimal, InvalidOperation


def number(value, *, positive=False):
    try: n=Decimal(str(value))
    except InvalidOperation: raise ValueError('Invalid strategy number') from None
    if not n.is_finite() or n < 0 or (positive and n == 0):
        raise ValueError('Strategy number must be finite and nonnegative')
    return n


def evaluate(policy, candles, *, now_ms, bid, ask, quote_ms, position=None,
             paused=True, unresolved_order=False, realized_loss_today='0',
             entries_today=0, last_entry_signal_ms=None):
    def answer(signal, reason, **extra):
        return {'mode':'SIMULATION_ONLY','signal':signal,'reason':reason,
                'permits_live_order':False,**extra}
    if (policy.get('mode') != 'SIMULATION_ONLY' or policy.get('live_activation') is not False
            or policy.get('live_budget_usdt') is not None):
        raise ValueError('This evaluator cannot activate or authorize live trading')
    if policy.get('symbol') != 'BTCUSDT' or policy.get('max_positions') != 1:
        raise ValueError('Proposal supports BTCUSDT and one position only')
    if any(policy.get(k) is not False for k in ['leverage','averaging_down','withdrawals','commission_collection']):
        raise ValueError('Unsupported proposed policy')
    fast, slow, minutes=policy['fast_sma'],policy['slow_sma'],policy['interval_minutes']
    if any(type(v) is not int for v in [fast,slow,minutes]) or not 1 <= fast < slow or minutes != 15:
        raise ValueError('Invalid closed-candle moving-average settings')
    interval=minutes*60*1000
    if type(now_ms) is not int or type(quote_ms) is not int:
        raise ValueError('Integer millisecond timestamps required')
    max_age=number(policy['quote_max_age_seconds'],positive=True)*1000
    if not 0 <= now_ms-quote_ms <= max_age:
        return answer('HALT','Price quote is stale or future-dated')
    bid,ask=number(bid,positive=True),number(ask,positive=True)
    if bid > ask: return answer('HALT','Crossed or invalid quote')
    if unresolved_order: return answer('HALT','An outstanding order must be reconciled first')
    tp=number(policy['take_profit_net_fraction'],positive=True)
    sl=number(policy['stop_loss_net_fraction'],positive=True)
    fee=number(policy['simulation_exit_fee_rate'])
    if tp >= 1 or sl >= 1 or fee > Decimal('.05'):
        raise ValueError('Invalid simulated exit thresholds or fee rate')
    # Risk checks use the fresh bid even when entry candles are not yet available.
    if position is not None:
        qty,cost=number(position['qty'],positive=True),number(position['cost_usdt'],positive=True)
        net_return=(qty*bid*(1-fee)-cost)/cost
        if net_return <= -sl:
            return answer('PAPER_EXIT_SIGNAL','Simulated net stop threshold reached',estimated_net_return=str(net_return))
        if net_return >= tp:
            return answer('PAPER_EXIT_SIGNAL','Simulated net profit threshold reached',estimated_net_return=str(net_return))
    if len(candles) < slow+1:
        return answer('WAIT','Not enough completed candles for a crossover')
    bars=candles[-(slow+1):]
    closes=[]
    previous=None
    for bar in bars:
        stamp=bar['close_ms']
        if (type(stamp) is not int or stamp % interval or stamp > now_ms
                or (previous is not None and stamp-previous != interval)):
            return answer('HALT','Candles must be consecutive, completed 15-minute bars')
        closes.append(number(bar['close'],positive=True))
        previous=stamp
    if now_ms-bars[-1]['close_ms'] >= interval:
        return answer('HALT','Completed-candle history is stale')
    previous_fast=sum(closes[-fast-1:-1])/fast
    previous_slow=sum(closes[-slow-1:-1])/slow
    current_fast=sum(closes[-fast:])/fast
    current_slow=sum(closes[-slow:])/slow
    up=previous_fast <= previous_slow and current_fast > current_slow
    down=previous_fast >= previous_slow and current_fast < current_slow
    if position is not None:
        return answer('PAPER_EXIT_SIGNAL' if down else 'HOLD',
                      'Bearish closed-candle crossover' if down else 'No simulated exit trigger')
    if paused: return answer('PAUSED','New entries are paused')
    if type(entries_today) is not int or entries_today < 0:
        raise ValueError('Invalid daily entry count')
    if entries_today >= policy['max_entries_per_day']:
        return answer('PAUSED','Daily entry limit reached')
    loss_limit=number(policy['simulation_allocation_usdt'],positive=True)*number(policy['daily_realized_loss_fraction'],positive=True)
    if number(realized_loss_today) >= loss_limit:
        return answer('PAUSED','Daily realized-loss threshold reached; this is not a guaranteed loss cap')
    if (ask-bid)/ask > number(policy['max_entry_spread_fraction'],positive=True):
        return answer('WAIT','Entry spread exceeds the proposed bound')
    if last_entry_signal_ms is not None:
        if type(last_entry_signal_ms) is not int: raise ValueError('Invalid last entry signal timestamp')
        if last_entry_signal_ms >= bars[-1]['close_ms']:
            return answer('WAIT','This entry candle was already consumed')
    return answer('PAPER_ENTRY_SIGNAL' if up else 'WAIT',
                  'Bullish closed-candle crossover' if up else 'No new bullish crossover',
                  candle_close_ms=bars[-1]['close_ms'])
