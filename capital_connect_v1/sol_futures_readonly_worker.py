"""Capital Connect SOLUSDT Futures TESTNET read-only worker.

This is a safe pre-execution worker: no order submission, no mainnet access.
Run with: python -m capital_connect_v1.sol_futures_readonly_worker
"""
import json
import os
import signal
import time
from .bybit_authenticated_probe import verify_testnet_credentials

POLL_SECONDS = 60
_STOP = False

def stop(_signum, _frame):
    global _STOP
    _STOP = True

def snapshot():
    result = verify_testnet_credentials()
    checks = result.get("read_only", {})
    ready = (result.get("environment") == "TESTNET"
             and result.get("authentication") == "VERIFIED"
             and all(checks.get(k) == "VERIFIED" for k in ("wallet", "positions", "orders")))
    return {
        "service": "capital-connect-sol-futures-readonly-worker",
        "market": "SOLUSDT",
        "category": "linear",
        "environment": "TESTNET",
        "authentication": result.get("authentication", "NOT_CONFIGURED"),
        "read_only_checks": checks,
        "read_only_ready": ready,
        "execution_enabled": False,
        "orders_submitted": 0,
        "exchange_side_protection_verified": False,
        "mainnet_verified": False,
    }

def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not _STOP:
        try:
            print("FUTURES_READONLY_WORKER " + json.dumps(snapshot(), sort_keys=True), flush=True)
        except Exception as error:
            print("FUTURES_READONLY_WORKER " + json.dumps({
                "environment": "TESTNET", "execution_enabled": False,
                "read_only_ready": False, "error_type": type(error).__name__
            }), flush=True)
        for _ in range(POLL_SECONDS):
            if _STOP:
                break
            time.sleep(1)

if __name__ == "__main__":
    main()
