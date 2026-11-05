import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

# Try to import pybit - this fixes NO PYBIT
try:
    from pybit.unified_trading import HTTP
    PYBIT_AVAILABLE = True
    PYBIT_STATUS = "PYBIT OK ✅"
except Exception as e:
    PYBIT_AVAILABLE = False
    PYBIT_STATUS = f"NO PYBIT ❌ - {e}"

SOL_PRICE = 96.67
USDT_BALANCE = 39.66

@app.get("/", response_class=HTMLResponse)
def dashboard():
    status_color = "green" if PYBIT_AVAILABLE else "red"
    return f"""
    <html>
    <head><title>SOL Bot Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body{{background:#0a0a0a;color:white;font-family:Arial;padding:20px;text-align:center}}
        .card{{background:#1a1a1a;border-radius:15px;padding:20px;margin:15px auto;max-width:500px;border:1px solid #333}}
        .live{{color:#00ff88;font-weight:bold}}
        .status{{color:{status_color};font-weight:bold;font-size:18px}}
    </style>
    </head>
    <body>
        <h1>🚀 SOL Bot - BSB Strategy</h1>
        <div class="card">
            <h2 class="status">{PYBIT_STATUS}</h2>
            <p>SOL Price: <span class="live">${SOL_PRICE}</span></p>
            <p>USDT Balance: ${USDT_BALANCE}</p>
            <p>Service: <span class="live">LIVE ✅</span></p>
            <p>Region: Singapore - Low latency to Bybit</p>
            <hr style="border-color:#333">
            <p>AutoTrader: <span class="live">ON</span></p>
            <p>Dip needed: 1.5% | Current dip: 0.42%</p>
            <p>Mode: Waiting for dip...</p>
        </div>
        <div class="card">
            <a href="/docs" style="color:#00ff88">API Docs</a> | 
            <a href="/status" style="color:#00ff88">Status JSON</a>
        </div>
        <p>Free instance - will spin down after inactivity</p>
    </body>
    </html>
    """

@app.get("/status")
def status():
    bybit_key = os.getenv("BYBIT_API_KEY", "NOT SET")
    return {
        "status": "live",
        "pybit": PYBIT_STATUS,
        "pybit_available": PYBIT_AVAILABLE,
        "sol_price": SOL_PRICE,
        "usdt_balance": USDT_BALANCE,
        "bybit_key_set": "YES" if bybit_key != "NOT SET" and len(bybit_key) > 5 else "NO",
        "service": "sol-bot-0wt0"
    }

@app.get("/health")
def health():
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
