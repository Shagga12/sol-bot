"""Read-only Bybit TESTNET SOLUSDT linear contract inspection.

No API credentials, order placement, private endpoints or mainnet fallback.
"""
import json
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from urllib.request import Request, build_opener, HTTPRedirectHandler

URL = "https://api-testnet.bybit.com/v5/market/instruments-info?category=linear&symbol=SOLUSDT"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def verify_contract(payload):
    if payload.get("retCode") != 0:
        raise ValueError("Testnet rejected instrument request")
    rows = payload.get("result", {}).get("list", [])
    if len(rows) != 1:
        raise ValueError("Expected exactly one SOLUSDT instrument")
    item = rows[0]
    if item.get("symbol") != "SOLUSDT" or item.get("status") != "Trading":
        raise ValueError("SOLUSDT linear contract not trading")
    lot = item.get("lotSizeFilter", {})
    for key in ("qtyStep", "minOrderQty"):
        try:
            n = Decimal(str(lot[key]))
        except (KeyError, ValueError, InvalidOperation, TypeError):
            raise ValueError("Missing quantity rules") from None
        if not n.is_finite() or n <= 0:
            raise ValueError("Invalid quantity rules")
    # Size the proposed $10 margin / 3x position against exchange rules.
    # No price or quantity is sent to the exchange.
    from .futures_plan import proposed_plan
    plan = proposed_plan()
    tick = Decimal(str(lot["qtyStep"]))
    minimum = Decimal(str(lot["minOrderQty"]))
    min_notional = Decimal(str(lot.get("minNotionalValue", "0")))
    price_info = item.get("priceFilter", {})
    max_leverage = Decimal(str(item.get("leverageFilter", {}).get("maxLeverage", "0")))
    if max_leverage < plan.leverage:
        raise ValueError("3x leverage unavailable on testnet")
    # Instrument info does not supply a current tradable price: mark sizing
    # unverified rather than assume a price or declare order readiness.
    return {"symbol": "SOLUSDT", "testnet_contract": "VERIFIED",
            "qtyStep": str(tick), "minOrderQty": str(minimum),
            "minNotionalValue": str(min_notional),
            "maximum_notional_usdt": str(plan.maximum_notional_usdt),
            "leverage_available": True, "order_sizing": "NOT_VERIFIED_NO_PRICE",
            "exchange_protective_orders": "NOT_VERIFIED",
            "orders_submitted": 0}


def check(opener=None):
    client = opener or build_opener(NoRedirect)
    request = Request(URL, headers={"Accept": "application/json", "User-Agent": "CapitalConnect-Testnet-ReadOnly"})
    with client.open(request, timeout=12) as response:
        if response.status != 200:
            raise ValueError("Testnet HTTP error")
        data = json.load(response)
    return verify_contract(data)


if __name__ == "__main__":
    try:
        print(json.dumps(check()))
    except Exception as error:
        print(json.dumps({"testnet_contract": "NOT_VERIFIED",
                          "error_category": type(error).__name__,
                          "orders_submitted": 0}))
        raise SystemExit(1)
