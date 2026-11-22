"""Capital Connect Futures dashboard — read-only, no trading endpoints.

Serves a restricted dashboard and truthful testnet status. No repository listing.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from capital_connect_v1.bybit_authenticated_probe import verify_testnet_credentials

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "futures_dashboard.html"
BSB_HTML = ROOT / "bsb_futures_paper.html"

AUTH_STATUS = {"authentication":"CHECKING","read_only":{}}

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        if urlsplit(self.path).path == "/health":
            return self.reply("", "application/json")
        return self.reply("", "text/plain", 200 if urlsplit(self.path).path == "/" else 404)
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            return self.reply(json.dumps({"status":"ok","environment":"testnet","orders_enabled":False}), "application/json")
        if path == "/":
            return self.reply(HTML.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if path == "/bsb":
            return self.reply(BSB_HTML.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if path == "/api/market":
            try:
                with urlopen("https://api-testnet.bybit.com/v5/market/tickers?category=linear&symbol=SOLUSDT", timeout=6) as response:
                    payload = json.load(response)
                ticker = payload.get("result", {}).get("list", [])[0]
                return self.reply(json.dumps({"source":"BYBIT_TESTNET_PUBLIC","symbol":"SOLUSDT","last_price":ticker["lastPrice"],"mark_price":ticker.get("markPrice"),"price_change_24h":ticker.get("price24hPcnt"),"live":True}), "application/json")
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                return self.reply(json.dumps({"source":"BYBIT_TESTNET_PUBLIC","live":False,"error":"Market data unavailable"}), "application/json", 503)
        if path == "/api/status":
            return self.reply(json.dumps({
                "name":"Capital Connect","market":"SOLUSDT","category":"linear",
                "environment":"testnet","execution":"READ_ONLY_CONNECTED" if AUTH_STATUS.get("authentication") == "VERIFIED" else "NOT_CONNECTED",
                "read_only_checks":AUTH_STATUS.get("read_only",{}),
                "orders_enabled":False,"exchange_protection":"NOT_VERIFIED",
                "dashboard_controls":"LOCKED_PENDING_FUTURES_WORKER",
                "note":"Authenticated read-only Testnet checks passed; order execution and exchange protection remain unverified." if AUTH_STATUS.get("authentication") == "VERIFIED" else "Testnet authentication is not verified; trading is disabled."
            }), "application/json")
        self.reply('{"error":"not found"}', "application/json", 404)
    def reply(self, body, content_type, status=200):
        raw=body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("X-Frame-Options","DENY")
        self.send_header("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass

if __name__ == "__main__":
    AUTH_STATUS.update(verify_testnet_credentials())
    print("BYBIT_TESTNET_AUTH_CHECK " + json.dumps(AUTH_STATUS), flush=True)
    ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
