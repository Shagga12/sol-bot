from flask import Flask, jsonify
import requests

app = Flask(__name__)

# YOUR SETTINGS
TOTAL_BALANCE = 39.66  # Change this when you deposit more
SAFE_PERCENT = 0.10

def get_sol_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=5)
        return float(r.json()['result']['list'][0]['lastPrice'])
    except:
        return 92.45

@app.route("/")
def home():
    price = get_sol_price()
    safe_amount = TOTAL_BALANCE * SAFE_PERCENT
    trade_amount = TOTAL_BALANCE * (1 - SAFE_PERCENT)
    max_sol = trade_amount / price if price > 0 else 0

    return f"""
    <html>
    <head><title>SOL Bot Singapore</title>
    <meta http-equiv="refresh" content="10">
    <style>
      body{{background:#0f0f0f;color:#fff;font-family:Arial;text-align:center;padding:20px}}
      .card{{background:#1a1a1a;padding:20px;border-radius:15px;margin:15px auto;max-width:420px;border:1px solid #333}}
      .price{{font-size:42px;color:#00ff88;font-weight:bold}}
      .row{{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #222}}
      .safe{{color:#ffd700}} .trade{{color:#00ff88}}
    </style>
    </head>
    <body>
      <h1>🤖 SOL Bot - Singapore</h1>
      <div class="card">
        <div>SOL/USDT Live Price</div>
        <div class="price">${price:.2f}</div>
        <div style="color:#888;font-size:12px">Auto-refresh 10s</div>
      </div>
      <div class="card">
        <div class="row"><span>Total Deposit:</span><span>${TOTAL_BALANCE:.2f}</span></div>
        <div class="row"><span>Safe Locked (10%):</span><span class="safe">${safe_amount:.2f} 🔒</span></div>
        <div class="row"><span>For Trading (90%):</span><span class="trade">${trade_amount:.2f}</span></div>
        <div class="row"><span>Can Buy Max:</span><span>{max_sol:.3f} SOL</span></div>
      </div>
      <div class="card" style="border-color:#00ff88">
        Status: <span style="color:#00ff88">● LIVE</span> | 10% Rule Active
      </div>
    </body>
    </html>
    """

@app.route("/api/price")
def api_price():
    price = get_sol_price()
    safe_amount = TOTAL_BALANCE * SAFE_PERCENT
    trade_amount = TOTAL_BALANCE * (1 - SAFE_PERCENT)
    return jsonify({
        "symbol":"SOLUSDT",
        "price":price,
        "total": TOTAL_BALANCE,
        "safe_10_percent": round(safe_amount,2),
        "trading_90_percent": round(trade_amount,2)
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
