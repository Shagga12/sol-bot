"""Capital Connect AI Quant V1: safe, isolated demo signal engine.
No authenticated exchange calls or order placement.
"""
from dataclasses import dataclass
from decimal import Decimal
import json
from urllib.parse import urlencode
from urllib.request import urlopen

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")
BASE_URL = "https://api.bybit.com"
LIVE_ORDER_EXECUTION = False

@dataclass(frozen=True)
class Signal:
    symbol: str
    price: Decimal
    mode: str = "DEMO"
    action: str = "WAIT"

def get_public_price(symbol: str) -> Decimal:
    if symbol not in SYMBOLS:
        raise ValueError("Unsupported symbol")
    url = BASE_URL + "/v5/market/tickers?" + urlencode({"category": "spot", "symbol": symbol})
    with urlopen(url, timeout=10) as response:
        data = json.load(response)
    if data.get("retCode") != 0 or not data.get("result", {}).get("list"):
        raise RuntimeError("Market data unavailable; trading halted")
    price = Decimal(data["result"]["list"][0]["lastPrice"])
    if not price.is_finite() or price <= 0:
        raise RuntimeError("Invalid market price; trading halted")
    return price

def run_scan() -> list[Signal]:
    return [Signal(symbol=s, price=get_public_price(s)) for s in SYMBOLS]

if __name__ == "__main__":
    for item in run_scan():
        print(json.dumps({"symbol": item.symbol, "price": str(item.price), "mode": item.mode,
                          "action": item.action, "live_order_execution": LIVE_ORDER_EXECUTION}))
