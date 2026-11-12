"""Offline Bybit spot limit-IOC planner. Builds data only; never submits orders.

Inputs must be refreshed from the eligible exchange/account before each use.
Fee reserve is a planning bound, not an assertion about actual fee currency.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP

PAIRS = {'BTCUSDT', 'SOLUSDT', 'ETHUSDT', 'BNBUSDT'}
CAP = Decimal('20')
SLIPPAGE = Decimal('0.005')


def number(value, positive=False):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid numeric input') from None
    if not n.is_finite() or n < 0 or (positive and n == 0):
        raise ValueError('Invalid nonnegative amount')
    return n


def fresh(now, observed, age):
    delta = number(now) - number(observed)
    if delta < 0 or delta > age:
        raise ValueError('Stale or future-dated source data')


def rounded(n, step, direction):
    return (n / step).to_integral_value(rounding=direction) * step


def plan_buy(*, instrument, instrument_at, bid, ask, quote_at, now,
             available_usdt, balance_at, committed_usdt, budget, fee_reserve_rate,
             order_link_id):
    """Pure planner: validate a <=20 USDT total allocation and build limit IOC.

    available_usdt must be independently verified spendable funds, not raw
    walletBalance. committed_usdt includes open positions and reserved orders.
    Pending/unknown orders and account permissions need separate reconciliation.
    """
    fresh(now, quote_at, 5)
    fresh(now, balance_at, 5)
    fresh(now, instrument_at, 300)
    symbol = instrument.get('symbol')
    if (symbol not in PAIRS or instrument.get('quoteCoin') != 'USDT'
            or instrument.get('baseCoin') != symbol[:-4]
            or instrument.get('status') != 'Trading'
            or instrument.get('isPreListing', False)):
        raise ValueError('Unsupported or inactive spot instrument')
    if not isinstance(order_link_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}', order_link_id):
        raise ValueError('Invalid unique client order ID')
    bid, ask = number(bid, True), number(ask, True)
    if bid > ask or (ask-bid)/ask > Decimal('.01'):
        raise ValueError('Invalid or excessive spread')
    available, committed, budget, fee = map(number, (available_usdt, committed_usdt, budget, fee_reserve_rate))
    if fee > Decimal('.05') or budget <= 0 or budget > available or committed+budget > CAP:
        raise ValueError('Budget, allocation, or fee reserve rejected')
    try:
        lot = instrument['lotSizeFilter']
        step = number(lot['basePrecision'], True)
        tick = number(instrument['priceFilter']['tickSize'], True)
        minimum = number(lot['minOrderAmt'], True)
        maximum_qty = number(lot['maxLimitOrderQty'], True)
    except (KeyError, TypeError):
        raise ValueError('Incomplete current instrument filters') from None
    price = rounded(ask*(1+SLIPPAGE), tick, ROUND_UP)
    # Tick rounding must not silently raise the intended slippage cap.
    if price > ask*(1+SLIPPAGE):
        price = rounded(ask*(1+SLIPPAGE), tick, ROUND_DOWN)
    if price < ask:
        raise ValueError('No valid price tick inside the slippage bound')
    qty = rounded(budget/(price*(1+fee)), step, ROUND_DOWN)
    notional = qty*price
    reserve = notional*fee
    if qty <= 0 or qty > maximum_qty or notional < minimum:
        raise ValueError('Rounded order violates size filters')
    return {
        'mode': 'PLAN_ONLY',
        'maximum_quote_with_fee_reserve': format(notional+reserve, 'f'),
        'fee_reserve_usdt': format(reserve, 'f'),
        'payload': {'category': 'spot', 'symbol': symbol, 'side': 'Buy',
                    'orderType': 'Limit', 'timeInForce': 'IOC', 'isLeverage': 0,
                    'qty': format(qty, 'f'), 'price': format(price, 'f'),
                    'orderLinkId': order_link_id},
    }


def plan_sell(*, instrument, instrument_at, bid, ask, quote_at, now,
              spendable_base, balance_at, bot_owned_qty, requested_qty,
              base_fee_reserve_rate, order_link_id):
    """Offline sell plan: never sell externally owned coins or borrow.

    base_fee_reserve_rate must come from an independently verified fee policy.
    A nonzero reserve may leave dust; never increase quantity to meet a minimum.
    """
    fresh(now, quote_at, 5)
    fresh(now, balance_at, 5)
    fresh(now, instrument_at, 300)
    symbol = instrument.get('symbol')
    if (symbol not in PAIRS or instrument.get('quoteCoin') != 'USDT'
            or instrument.get('baseCoin') != symbol[:-4]
            or instrument.get('status') != 'Trading' or instrument.get('isPreListing', False)):
        raise ValueError('Unsupported or inactive spot instrument')
    if not isinstance(order_link_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,36}',order_link_id):
        raise ValueError('Invalid unique client order ID')
    bid, ask = number(bid,True), number(ask,True)
    if bid > ask or (ask-bid)/ask > Decimal('.01'):
        raise ValueError('Invalid or excessive spread')
    owned, available, requested, fee = map(number,(bot_owned_qty,spendable_base,requested_qty,base_fee_reserve_rate))
    if requested <= 0 or fee > Decimal('.05'):
        raise ValueError('Invalid sell quantity or fee bound')
    try:
        lot = instrument['lotSizeFilter']
        step = number(lot['basePrecision'],True)
        tick = number(instrument['priceFilter']['tickSize'],True)
        minimum = number(lot['minOrderAmt'],True)
        maximum = number(lot['maxLimitOrderQty'],True)
    except (KeyError,TypeError):
        raise ValueError('Incomplete current instrument filters') from None
    qty = rounded(requested,step,ROUND_DOWN)
    fee_reserve = qty*fee
    price = rounded(bid*(1-SLIPPAGE),tick,ROUND_UP)
    if price > bid:
        raise ValueError('No valid price tick inside the slippage bound')
    if qty <= 0 or qty+fee_reserve > min(owned,available):
        raise ValueError('Sell exceeds verified holdings including base fee reserve')
    if qty > maximum or qty*price < minimum:
        raise ValueError('Sell violates size filters; residual dust must remain unsold')
    return {'mode':'PLAN_ONLY', 'base_fee_reserve':format(fee_reserve,'f'),
            'payload':{'category':'spot','symbol':symbol,'side':'Sell','orderType':'Limit',
                       'timeInForce':'IOC','isLeverage':0,'qty':format(qty,'f'),
                       'price':format(price,'f'),'orderLinkId':order_link_id}}
