"""Capital Connect SOLUSDT Futures paper-trading engine.

No network access, credentials, exchange requests or real-money order execution.
Prices are caller-supplied. State changes only on explicit START/STOP.
"""
from dataclasses import dataclass
from decimal import Decimal
from .futures_plan import proposed_plan, dec


@dataclass
class PaperPosition:
    side: str
    entry: Decimal
    quantity: Decimal
    stop: Decimal
    target: Decimal


class SOLFuturesPaperBot:
    def __init__(self):
        self.plan = proposed_plan()
        self.running = False
        self.position = None
        self.realized_pnl = Decimal("0")
        self.events = []

    def start(self):
        self.running = True
        self.events.append("START")

    def stop(self):
        self.running = False
        self.events.append("STOP")
        # STOP prevents new entries; it does not silently remove protection
        # from a previously opened simulated position.

    def enter(self, side, price):
        if not self.running:
            raise ValueError("Bot is stopped")
        if self.position is not None:
            raise ValueError("Position already open")
        if side not in ("Long", "Short"):
            raise ValueError("Invalid side")
        price = dec(price)
        if price <= 0:
            raise ValueError("Price must be positive")
        qty = self.plan.maximum_notional_usdt / price
        sl = dec(self.plan.stop_loss_fraction)
        tp = dec(self.plan.take_profit_fraction)
        stop = price * (1 - sl if side == "Long" else 1 + sl)
        target = price * (1 + tp if side == "Long" else 1 - tp)
        self.position = PaperPosition(side, price, qty, stop, target)
        self.events.append("PAPER_ENTRY_" + side)
        return self.position

    def tick(self, price):
        price = dec(price)
        if price <= 0:
            raise ValueError("Price must be positive")
        pos = self.position
        if pos is None:
            return None
        if pos.side == "Long":
            reason = "STOP_LOSS" if price <= pos.stop else ("TAKE_PROFIT" if price >= pos.target else None)
        else:
            reason = "STOP_LOSS" if price >= pos.stop else ("TAKE_PROFIT" if price <= pos.target else None)
        if reason is None:
            return None
        # Simulated fills use the protective threshold, not a guarantee
        # of achievable exchange execution or slippage.
        fill = pos.stop if reason == "STOP_LOSS" else pos.target
        pnl = (fill - pos.entry) * pos.quantity * (1 if pos.side == "Long" else -1)
        self.realized_pnl += pnl
        self.position = None
        self.events.append("PAPER_EXIT_" + reason)
        return {"reason": reason, "pnl_before_fees": pnl, "fill_assumption": fill}
