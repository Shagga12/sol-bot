"""Read-only Bybit SOLUSDT linear Futures market preflight.

No credentials, account mutations, or order endpoints. This does not certify
account permissions, fills, or exchange-side stop-loss/take-profit.
"""
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from capital_connect_v1.live import NoRedirect

HOSTS = {"testnet": "https://api-testnet.bybit.com", "mainnet": "https://api.bybit.com"}

class FuturesPreflightError(RuntimeError):
    pass

def positive(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise FuturesPreflightError("Invalid exchange numeric field") from None
    if not n.is_finite() or n <= 0:
        raise FuturesPreflightError("Invalid exchange numeric field")
    return n

def inspect_market(environment="testnet", opener=None):
    if environment not in HOSTS:
        raise FuturesPreflightError("Invalid environment")
    opener = opener or build_opener(NoRedirect)
    url = HOSTS[environment] + "/v5/market/instruments-info?" + urlencode(
        {"category": "linear", "symbol": "SOLUSDT"})
    try:
        with opener.open(Request(url, method="GET"), timeout=10) as response:
            payload = json.load(response)
    except Exception:
        raise FuturesPreflightError("Market inspection unavailable") from None
    if payload.get("retCode") != 0:
        raise FuturesPreflightError("Exchange rejected market inspection")
    rows = payload.get("result", {}).get("list", [])
    if len(rows) != 1:
        raise FuturesPreflightError("Expected one SOLUSDT instrument")
    item = rows[0]
    if (item.get("symbol") != "SOLUSDT" or item.get("status") != "Trading"
            or item.get("contractType") != "LinearPerpetual"
            or item.get("settleCoin") != "USDT"):
        raise FuturesPreflightError("SOLUSDT linear perpetual not tradable")
    lot = item.get("lotSizeFilter") or {}
    price = item.get("priceFilter") or {}
    return {
        "environment": environment, "symbol": "SOLUSDT",
        "category": "linear", "market_trading": True,
        "min_order_qty": str(positive(lot.get("minOrderQty"))),
        "qty_step": str(positive(lot.get("qtyStep"))),
        "tick_size": str(positive(price.get("tickSize"))),
        "orders_enabled": False, "exchange_protection_verified": False,
    }
