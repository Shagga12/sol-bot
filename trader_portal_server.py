"""Isolated trader portal foundation. No deposits or order execution endpoints.

Run behind HTTPS with TRADER_SESSION_SECRET and an encrypted persistent volume.
Accounts must be provisioned by an authorized operator using a separate workflow.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DB_PATH = os.environ.get("TRADER_DB_PATH", "/var/data/traders.sqlite3")
SESSION_SECRET = os.environ.get("TRADER_SESSION_SECRET", "")
SESSION_TTL = 3600
MAX_BODY = 4096

def db():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection

def initialize():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          password_salt BLOB NOT NULL, password_hash BLOB NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('trader','super_admin')),
          enabled INTEGER NOT NULL DEFAULT 1)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS sessions (
          token_hash BLOB PRIMARY KEY, user_id INTEGER NOT NULL,
          expires_at INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS audit_events (
          id INTEGER PRIMARY KEY, user_id INTEGER, event TEXT NOT NULL,
          occurred_at INTEGER NOT NULL)""")

def hash_password(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)

def create_user(username, password, role="trader"):
    """Operator-only provisioning; never exposed as an HTTP route."""
    if role not in ("trader", "super_admin") or not (3 <= len(username) <= 64):
        raise ValueError("Invalid user")
    if len(password) < 14 or len(password) > 256:
        raise ValueError("Password must be 14-256 characters")
    salt = secrets.token_bytes(16)
    with db() as connection:
        connection.execute("INSERT INTO users(username,password_salt,password_hash,role) VALUES(?,?,?,?)",
                           (username, salt, hash_password(password, salt), role))

def token_hash(token):
    return hmac.new(SESSION_SECRET.encode(), token.encode(), hashlib.sha256).digest()

def authenticate(username, password):
    with db() as connection:
        row = connection.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
    # Avoid fast rejection for unknown users.
    salt = row["password_salt"] if row else b"\0" * 16
    candidate = hash_password(password, salt)
    if row and hmac.compare_digest(candidate, row["password_hash"]):
        return row
    return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def respond(self, status, data, extra_headers=()):
        body = json.dumps(data).encode()
        self.send_response(status)
        for key, value in extra_headers:
            self.send_header(key, value)
        for key, value in (
            ("Content-Type", "application/json; charset=utf-8"),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"),
            ("Referrer-Policy", "no-referrer"),
            ("Content-Length", str(len(body)),
        ):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
            token = jar["trader_session"].value
            if len(token) != 64:
                return None
        except (KeyError, cookies.CookieError):
            return None
        with db() as connection:
            return connection.execute("""SELECT users.id,users.username,users.role
                FROM sessions JOIN users ON users.id=sessions.user_id
                WHERE sessions.token_hash=? AND sessions.expires_at>? AND users.enabled=1""",
                (token_hash(token), int(time.time()))).fetchone()

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if not 0 < size <= MAX_BODY or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return None
        try:
            value = json.loads(self.rfile.read(size))
            return value if isinstance(value, dict) else None
        except (ValueError, UnicodeDecodeError):
            return None

    def origin_ok(self):
        origin = os.environ.get("TRADER_PUBLIC_ORIGIN", "")
        return bool(origin) and self.headers.get("Origin") == origin

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            return self.respond(200, {"status": "ok", "orders_enabled": False, "deposits_enabled": False})
        if path == "/api/me":
            user = self.session()
            if not user:
                return self.respond(401, {"error": "Authentication required"})
            return self.respond(200, {"username": user["username"], "role": user["role"],
                                      "balance": None, "positions": [], "trades": [],
                                      "orders_enabled": False, "deposits_enabled": False})
        return self.respond(404, {"error": "Not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self.origin_ok():
            return self.respond(403, {"error": "Forbidden"})
        if path == "/api/login":
            data = self.read_json()
            if not data or not isinstance(data.get("username"), str) or not isinstance(data.get("password"), str):
                return self.respond(400, {"error": "Invalid request"})
            if len(data["username"]) > 64 or len(data["password"]) > 256:
                return self.respond(400, {"error": "Invalid request"})
            user = authenticate(data["username"], data["password"])
            if not user:
                time.sleep(.3)
                return self.respond(401, {"error": "Invalid credentials"})
            token = secrets.token_hex(32)
            with db() as connection:
                connection.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                                   (token_hash(token), user["id"], int(time.time()) + SESSION_TTL))
                connection.execute("INSERT INTO audit_events(user_id,event,occurred_at) VALUES(?,?,?)",
                                   (user["id"], "login", int(time.time())))
            return self.respond(200, {"authenticated": True, "role": user["role"]},
                [("Set-Cookie", "trader_session=" + token + "; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=3600")])
        if path == "/api/logout":
            user = self.session()
            jar = cookies.SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
                token = jar["trader_session"].value
                with db() as connection:
                    connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))
            except (KeyError, cookies.CookieError):
                pass
            return self.respond(200, {"logged_out": True},
                [("Set-Cookie", "trader_session=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0")])
        return self.respond(404, {"error": "Not found"})

if __name__ == "__main__":
    if len(SESSION_SECRET) < 32:
        raise SystemExit("Set a strong TRADER_SESSION_SECRET before starting")
    initialize()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
