"""Fail-closed proposed Bybit SOLUSDT linear futures configuration.

This module is intentionally NOT wired into the existing spot execution worker.
It never submits exchange orders. A separate futures execution implementation
must pass exchange testnet entry, attached TP/SL, reconciliation and restart tests.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

class FuturesConfigurationError(ValueError):
    pass

def dec(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise FuturesConfigurationError("Invalid numeric setting") from None
    if not d.is_finite():
        raise FuturesConfigurationError("Non-finite setting")
    return d

@dataclass(frozen=True)
class SOLFuturesPlan:
    symbol: str = "SOLUSDT"
    category: str = "linear"
    margin_mode: str = "ISOLATED"
    leverage: int = 3
    margin_usdt: str = "10"
    stop_loss_fraction: str = "0.01"
    take_profit_fraction: str = "0.04"
    environment: str = "testnet"
    orders_enabled: bool = False

    def validate(self):
        if self.symbol != "SOLUSDT" or self.category != "linear":
            raise FuturesConfigurationError("Only SOLUSDT linear futures is approved")
        if self.margin_mode != "ISOLATED" or type(self.leverage) is not int or self.leverage != 3:
            raise FuturesConfigurationError("Require 3x isolated margin")
        if dec(self.margin_usdt) != Decimal("10"):
            raise FuturesConfigurationError("Margin budget must equal 10 USDT")
        if dec(self.stop_loss_fraction) != Decimal("0.01") or dec(self.take_profit_fraction) != Decimal("0.04"):
            raise FuturesConfigurationError("Unapproved exit thresholds")
        if self.environment != "testnet" or self.orders_enabled:
            raise FuturesConfigurationError("Futures release is testnet inspection only")
        return self

    @property
    def maximum_notional_usdt(self):
        self.validate()
        return dec(self.margin_usdt) * self.leverage

def proposed_plan():
    return SOLFuturesPlan().validate()
