"""Isolated Bybit spot order adapter. Not imported by the running DEMO worker.

No orders are submitted unless explicitly armed by an operator at invocation.
Keep withdrawals disabled on the dedicated trading API key.
"""
import hashlib
import hmac
import json
import os
import time
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = "https://api.bybit.com"
SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def positive(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid decimal")
    if not result.is_finite() or result <= 0:
        raise ValueError("Amount must be positive and finite")
    return result

def api(method, path, params=None, key=None, secret=None):
    if path not in {"/v5/market/instruments-info", "/v5/account/wallet-balance", "/v5/order/create"}:
        raise ValueError("Endpoint not permitted")
    if method == "POST" and path != "/v5/order/create":
        raise ValueError("POST not permitted")
    if method == "GET" and path == "/v5/order/create":
        raise ValueError("GET not permitted for orders")
    params = params or {}
    payload = urlencode(params) if method == "GET" else json.dumps(params, separators=(",", ":"))
    url = BASE + path + ("?" + payload if method == "GET" and payload else "")
    headers = {"Content-Type": "application/json"}
    if path != "/v5/market/instruments-info":
        if not key or not secret:
            raise ValueError("Credentials required")
        ts = str(int(time.time() * 1000))
        headers.update({"X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": ts,
                        "X-BAPI-RECV-WINDOW": "5000",
                        "X-BAPI-SIGN": hmac.new(secret.encode(), (ts + key + "5000" + payload).encode(), hashlib.sha256).hexdigest()})
    req = Request(url, data=payload.encode() if method == "POST" else None, headers=headers, method=method)
    with build_opener(NoRedirect).open(req, timeout=12) as response:
        result = json.load(response)
    if result.get("retCode") != 0:
        raise RuntimeError("Bybit rejected request (code %s)" % result.get("retCode"))
    return result.get("result", {})

def prepare_buy(symbol, quote_usdt, key, secret):
    """Read-only preflight: enforce exchange min/max and available USDT."""
    if symbol not in SYMBOLS:
        raise ValueError("Unsupported symbol")
    amount = positive(quote_usdt)
    if amount > Decimal("10"):
        raise ValueError("Initial per-order risk cap is 10 USDT")
    info = api("GET", "/v5/market/instruments-info", {"category": "spot", "symbol": symbol})
    items = info.get("list", [])
    if len(items) != 1 or items[0].get("symbol") != symbol or items[0].get("status") != "Trading":
        raise RuntimeError("Spot instrument unavailable")
    lot = items[0].get("lotSizeFilter", {})
    minimum = positive(lot.get("minOrderAmt", "0"))
    maximum = positive(lot.get("maxMarketOrderQty", "0"))
    # maxMarketOrderQty is in base asset, not quote; do not compare directly.
    if amount < minimum:
        raise ValueError("Below exchange minimum quote amount")
    wallet = api("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED", "coin": "USDT"}, key, secret)
    entries = wallet.get("list", [])
    if len(entries) != 1 or entries[0].get("accountType") != "UNIFIED":
        raise RuntimeError("Unified wallet unavailable")
    coin = next((c for c in entries[0].get("coin", []) if c.get("coin") == "USDT"), None)
    if not coin:
        raise RuntimeError("USDT not present")
    # Wallet balance is not necessarily transferable/available under Unified margin.
    # Fail closed until an independently verified available-to-trade amount is supplied.
    return {"symbol": symbol, "quote_usdt": str(amount), "minimum_quote_usdt": str(minimum),
            "wallet_usdt": coin.get("walletBalance"), "ready_to_submit": False,
            "reason": "Available-to-trade funds and market quantity limits require verification"}

def submit_market_buy(symbol, quote_usdt, *, approved_available_usdt, approval_token):
    """Manual single-order gateway. Never called by the DEMO worker.

    An operator must explicitly set CAPITAL_LIVE_ORDERS=ENABLED and provide
    CAPITAL_ORDER_APPROVAL equal to approval_token for this one invocation.
    """
    if os.getenv("CAPITAL_LIVE_ORDERS") != "ENABLED" or not approval_token or os.getenv("CAPITAL_ORDER_APPROVAL") != approval_token:
        raise RuntimeError("Live order gateway disarmed")
    key, secret = os.getenv("BYBIT_TRADE_API_KEY"), os.getenv("BYBIT_TRADE_API_SECRET")
    if not key or not secret:
        raise RuntimeError("Dedicated trading credentials missing")
    preview = prepare_buy(symbol, quote_usdt, key, secret)
    amount = positive(quote_usdt)
    if positive(approved_available_usdt) < amount:
        raise RuntimeError("Insufficient independently verified available USDT")
    order_link_id = "cc-" + uuid.uuid4().hex[:24]
    return api("POST", "/v5/order/create", {
        "category": "spot", "symbol": symbol, "side": "Buy", "orderType": "Market",
        "qty": str(amount), "marketUnit": "quoteCoin", "timeInForce": "IOC",
        "orderLinkId": order_link_id}, key, secret)
