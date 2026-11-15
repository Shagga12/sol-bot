"""Build exchange-attached Spot protection using the bounded entry price.
Targets are estimates after fee assumptions, never guarantees of fill price.
"""
from decimal import Decimal as D, ROUND_CEILING
from .live import number, floor, Halt


def attach_protection(payload, config, rules, fee):
    if payload.get('category')!='spot' or payload.get('side')!='Buy' or payload.get('orderType')!='Limit':
        raise Halt('Protection attaches only to spot limit buys')
    fee=number(fee)
    if not 0 <= fee < D('.1'):raise Halt('Invalid protection fee')
    entry=number(payload['price'],True)
    tick=number(rules['priceFilter']['tickSize'],True)
    # Cover either base-denominated or quote-denominated entry fees conservatively.
    basis=entry*(1+fee)/(1-fee)
    take=(basis*(1+number(config.take_profit_fraction))/(1-fee)/tick).to_integral_value(rounding=ROUND_CEILING)*tick
    stop=(basis*(1-number(config.stop_loss_fraction))/(1-fee)/tick).to_integral_value(rounding=ROUND_CEILING)*tick
    if not 0 < stop < entry < take:
        raise Halt('Fee assumptions leave no valid stop below entry')
    return {**payload,'takeProfit':format(take,'f'),'stopLoss':format(stop,'f'),
            'tpOrderType':'Market','slOrderType':'Market'}
