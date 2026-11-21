"""Read-only Bybit linear position protection verification.

This module does not submit orders or unlock real-money trading. It checks
exchange-reported position TP/SL fields, not locally simulated triggers.
"""
from decimal import Decimal, InvalidOperation

class ProtectionNotVerified(ValueError):
    pass

def _positive(value, name):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ProtectionNotVerified(f"{name} missing or invalid") from None
    if not number.is_finite() or number <= 0:
        raise ProtectionNotVerified(f"{name} must be positive")
    return number

def verify_linear_position(position, *, symbol="SOLUSDT"):
    """Return a protection summary only for an exact, protected linear position.

    A successful result proves only what this single exchange snapshot reports.
    It does not establish future fills, trigger reliability, or safe activation.
    """
    if not isinstance(position, dict):
        raise ProtectionNotVerified("Missing exchange position")
    if position.get("symbol") != symbol or symbol != "SOLUSDT":
        raise ProtectionNotVerified("Unexpected contract")
    if position.get("side") not in ("Buy", "Sell"):
        raise ProtectionNotVerified("Unexpected position side")
    qty = _positive(position.get("size"), "size")
    entry = _positive(position.get("avgPrice"), "entry")
    stop = _positive(position.get("stopLoss"), "exchange stop loss")
    take = _positive(position.get("takeProfit"), "exchange take profit")
    if position["side"] == "Buy" and not (stop < entry < take):
        raise ProtectionNotVerified("Long protection prices are not on opposite sides of entry")
    if position["side"] == "Sell" and not (take < entry < stop):
        raise ProtectionNotVerified("Short protection prices are not on opposite sides of entry")
    if position.get("tradeMode") != 1:
        raise ProtectionNotVerified("Isolated margin mode not confirmed")
    if _positive(position.get("leverage"), "leverage") != Decimal("3"):
        raise ProtectionNotVerified("Unexpected leverage")
    if position.get("tpslMode") != "Full":
        raise ProtectionNotVerified("Full-position TP/SL not confirmed")
    return {"symbol": symbol, "side": position["side"], "size": str(qty),
            "entry": str(entry), "stop_loss": str(stop),
            "take_profit": str(take), "exchange_snapshot_verified": True,
            "live_activation_authorized": False}
