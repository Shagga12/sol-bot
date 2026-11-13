"""Capital Connect read-only demo dashboard. No exchange order routes."""
import hmac
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from capital_connect_v1.paper import PaperLedger

DB_PATH = os.environ.get("CAPITAL_CONNECT_DB", "/var/data/capital-connect-demo.sqlite3")
ADMIN_TOKEN = os.environ.get("CAPITAL_CONNECT_ADMIN_TOKEN", "")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/health":
            return self.reply(200, {"service": "Capital Connect", "status": "ready", "mode": "DEMO"})
        if not ADMIN_TOKEN or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + ADMIN_TOKEN):
            return self.reply(401, {"error": "Administrator authentication required"})
        if route != "/api/demo/status":
            return self.reply(404, {"error": "Not found"})
        if not os.path.isfile(DB_PATH):
            return self.reply(503, {"error": "Demo ledger not mounted on this service"})
        try:
            ledger = PaperLedger(DB_PATH)
            try:
                result = ledger.status()
            finally:
                ledger.close()
        except Exception:
            return self.reply(503, {"error": "Demo ledger temporarily unavailable"})
        return self.reply(200, result)

    def reply(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    if not ADMIN_TOKEN:
        raise SystemExit("Set CAPITAL_CONNECT_ADMIN_TOKEN before starting dashboard")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
