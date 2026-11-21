"""Authenticated, read-only Bybit TESTNET credential probe.

Never submits orders or logs credentials/account balances.
"""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HOST = "https://api-testnet.bybit.com"

def read_only_request(key, secret, endpoint, query):
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    params = urlencode(query)
    signature = hmac.new(secret.encode(), (timestamp + key + recv_window + params).encode(), hashlib.sha256).hexdigest()
    request = Request(HOST + endpoint + "?" + params, headers={
        "X-BAPI-API-KEY": key, "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window, "X-BAPI-SIGN": signature,
        "Accept": "application/json",
    })
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def verify_testnet_credentials():
    key = os.environ.get("BYBIT_TESTNET_API_KEY", "")
    secret = os.environ.get("BYBIT_TESTNET_API_SECRET", "")
    if not key or not secret:
        return {"authentication": "NOT_CONFIGURED"}
    endpoints = (
        ("wallet", "/v5/account/wallet-balance", {"accountType": "UNIFIED"}),
        ("positions", "/v5/position/list", {"category": "linear", "symbol": "SOLUSDT"}),
        ("orders", "/v5/order/realtime", {"category": "linear", "symbol": "SOLUSDT"}),
    )
    checks = {}
    for name, endpoint, query in endpoints:
        try:
            result = read_only_request(key, secret, endpoint, query)
            checks[name] = "VERIFIED" if result.get("retCode") == 0 else "REJECTED"
        except Exception as error:
            checks[name] = "FAILED_" + type(error).__name__
    return {"authentication": "VERIFIED" if checks["wallet"] == "VERIFIED" else checks["wallet"],
            "environment": "TESTNET", "read_only": checks, "orders_submitted": 0}
