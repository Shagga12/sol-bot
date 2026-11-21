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

def verify_testnet_credentials():
    key = os.environ.get("BYBIT_TESTNET_API_KEY", "")
    secret = os.environ.get("BYBIT_TESTNET_API_SECRET", "")
    if not key or not secret:
        return {"authentication": "NOT_CONFIGURED"}
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    params = urlencode({"accountType": "UNIFIED"})
    signature = hmac.new(secret.encode(), (timestamp + key + recv_window + params).encode(), hashlib.sha256).hexdigest()
    request = Request(HOST + "/v5/account/wallet-balance?" + params, headers={
        "X-BAPI-API-KEY": key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": signature,
        "Accept": "application/json",
    })
    try:
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        return {"authentication": "VERIFIED" if result.get("retCode") == 0 else "REJECTED",
                "endpoint": "TESTNET_UNIFIED_WALLET_READ_ONLY",
                "orders_submitted": 0}
    except Exception as error:
        return {"authentication": "FAILED", "error_category": type(error).__name__,
                "orders_submitted": 0}
