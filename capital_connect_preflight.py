"""Capital Connect BTC/USDT preflight. Read-only; never submits orders."""
import os
import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode

BASE = "https://api.bybit.com"
SYMBOL = "BTCUSDT"
MAX_BUDGET_USDT = 20.0

def public_market():
    response = requests.get(
        BASE + "/v5/market/tickers",
        params={"category": "spot", "symbol": SYMBOL},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        raise RuntimeError("Bybit market data unavailable")
    return float(data["result"]["list"][0]["lastPrice"])

def read_only_balance():
    key = os.getenv("BYBIT_API_KEY")
    secret = os.getenv("BYBIT_API_SECRET")
    if not key or not secret:
        return {"status": "not_connected"}
    params = urlencode({"accountType": "UNIFIED", "coin": "USDT"})
    timestamp = str(int(time.time() * 1000))
    window = "5000"
    payload = timestamp + key + window + params
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": key,
        "X-BAPI-SIGN": signature,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": window,
    }
    response = requests.get(
        BASE + "/v5/account/wallet-balance?" + params,
        headers=headers, timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("retCode") != 0:
        return {"status": "connection_error", "code": data.get("retCode"),
                "message": data.get("retMsg")}
    return {"status": "connected_read_only", "account": "UNIFIED"}

if __name__ == "__main__":
    print("Capital Connect BTC/USDT | order execution DISABLED")
    print("Budget cap configured: 20 USDT (no funds reserved)")
    try:
        print("Market price:", public_market())
        print("Bybit connection:", read_only_balance())
    except (requests.RequestException, RuntimeError, ValueError) as error:
        print("Preflight failed:", type(error).__name__, str(error))
        raise SystemExit(1)
