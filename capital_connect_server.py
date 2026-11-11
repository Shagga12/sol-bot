"""Capital Connect safe preflight web service: no trading endpoints."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from urllib.parse import urlencode

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_error(404)
            return
        body = {"name": "Capital Connect", "mode": "PRE-FLIGHT ONLY",
                "symbol": "BTCUSDT", "max_budget_usdt": 20,
                "live_order_execution": False,
                "bybit_connection": "not_tested"}
        if self.path == "/":
            try:
                url = "https://api.bybit.com/v5/market/tickers?" + urlencode(
                    {"category": "spot", "symbol": "BTCUSDT"})
                with urlopen(url, timeout=8) as response:
                    result = json.load(response)
                if result.get("retCode") == 0 and result.get("result", {}).get("list"):
                    body["market_price_usdt"] = result["result"]["list"][0]["lastPrice"]
                else:
                    body["market_data"] = "unavailable"
            except Exception:
                body["market_data"] = "unavailable"
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
