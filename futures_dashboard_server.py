"""Capital Connect Futures dashboard — read-only, no trading endpoints.

Serves a restricted dashboard and truthful testnet status. No repository listing.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "futures_dashboard.html"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            return self.reply(json.dumps({"status":"ok","environment":"testnet","orders_enabled":False}), "application/json")
        if path == "/":
            return self.reply(HTML.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        if path == "/api/status":
            return self.reply(json.dumps({
                "name":"Capital Connect","market":"SOLUSDT","category":"linear",
                "environment":"testnet","execution":"NOT_CONNECTED",
                "orders_enabled":False,"exchange_protection":"NOT_VERIFIED",
                "dashboard_controls":"LOCKED_PENDING_FUTURES_WORKER",
                "note":"Public instrument tests passed; authenticated testnet order execution has not been verified."
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
    ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),Handler).serve_forever()
