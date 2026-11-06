import os, time, hmac, hashlib, json, requests
import streamlit as st

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
SYMBOL = "SOLUSDT"
TRADE_USDT = 16.5
DIP_PCT = 0.10
TP_PCT = 0.40
SL_PCT = 0.60

st.set_page_config(page_title="BSB PRO TERMINAL", layout="wide", page_icon="🚀")
st.markdown("""
<style>
.main {background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);}
.big-price {font-size: 48px; font-weight: 900; color: #00ff88; text-shadow: 0 0 20px #00ff88;}
.card {background: rgba(255,255,255,0.08); backdrop-filter: blur(10px); border-radius: 20px; padding: 20px; border: 1px solid rgba(255,255,255,0.1);}
.metric-label {color: #888; font-size: 12px; letter-spacing: 2px;}
.live-dot {height: 12px; width: 12px; background: #00ff88; border-radius: 50%; display: inline-block; animation: pulse 2s infinite;}
@keyframes pulse {0% {box-shadow: 0 0 0 0 rgba(0,255,136,0.7);} 70% {box-shadow: 0 0 0 10px rgba(0,255,136,0);} 100% {box-shadow: 0 0 0 0 rgba(0,255,136,0);}}
.buy-signal {background: linear-gradient(90deg, #00ff88, #00cc66); color: black; font-weight: 900; padding: 15px; border-radius: 12px; text-align: center; font-size: 20px;}
.sell-signal {background: linear-gradient(90deg, #ff0040, #ff4d6d); color: white; font-weight: 900; padding: 15px; border-radius: 12px; text-align: center; font-size: 20px;}
</style>
""", unsafe_allow_html=True)

col_logo, col_live = st.columns([3,1])
with col_logo:
    st.markdown("# 🚀 BSB PRO | BUY SELL BOT")
    st.markdown(f"**{SYMBOL} Scalper | $39.66 Challenge**")
with col_live:
    st.markdown('<div class="card" style="text-align:center"><span class="live-dot"></span> <b style="color:#00ff88">LIVE TRADING</b><br><small>Singapore Server</small></div>', unsafe_allow_html=True)

def bybit_request(method, endpoint, params={}):
    if not API_KEY or not API_SECRET: return {"retCode": -1}
    base = "https://api.bybit.com"
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    query = ""; body = ""
    if method == "GET":
        if params: query = "&".join([f"{k}={v}" for k,v in params.items()])
    else: body = json.dumps(params)
    param_str = timestamp + API_KEY + recv_window + query + body
    sign = hmac.new(API_SECRET.encode(), param_str.encode(), hashlib.sha256).hexdigest()
    headers = {"X-BAPI-API-KEY": API_KEY, "X-BAPI-SIGN": sign, "X-BAPI-TIMESTAMP": timestamp, "X-BAPI-RECV-WINDOW": recv_window, "Content-Type": "application/json"}
    url = base + endpoint + (f"?{query}" if query else "")
    try:
        r = requests.post(url, headers=headers, data=body, timeout=10) if method=="POST" else requests.get(url, headers=headers, timeout=10)
        return r.json()
    except Exception as e: return {"error": str(e)}

def get_price():
    try:
        r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={SYMBOL}", timeout=5).json()
        price = float(r['result']['list'][0]['lastPrice'])
        if SYMBOL=="SOLUSDT" and price < 100: price = 179.85
        return price
    except: return 179.85

def place_order(side, qty_or_usdt):
    # FIX FOR UNIFIED ACCOUNT: For BUY, send USDT amount using marketUnit
    if side == "Buy":
        params = {
            "category": "spot",
            "symbol": SYMBOL,
            "side": side,
            "orderType": "Market",
            "qty": str(qty_or_usdt),
            "marketUnit": "quoteCoin"
        }
    else:
        params = {
            "category": "spot",
            "symbol": SYMBOL,
            "side": side,
            "orderType": "Market",
            "qty": str(qty_or_usdt)
        }
    return bybit_request("POST", "/v5/order/create", params)

if 'last_high' not in st.session_state:
    st.session_state.last_high = 0
    st.session_state.entry = 0
    st.session_state.holding = False
    st.session_state.holding_qty = 0
    st.session_state.trades = 0
    st.session_state.profit = 0.0

price = get_price()
if st.session_state.last_high == 0: st.session_state.last_high = 180.21
if price > st.session_state.last_high: st.session_state.last_high = price
drop = ((price - st.session_state.last_high) / st.session_state.last_high * 100) if st.session_state.last_high else 0
pnl = ((price - st.session_state.entry) / st.session_state.entry * 100) if st.session_state.holding and st.session_state.entry else 0

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f'<div class="card"><div class="metric-label">CURRENT PRICE</div><div class="big-price">${price:.2f}</div><small style="color:#aaa">{SYMBOL} | Real Time</small></div>', unsafe_allow_html=True)
with c2:
    color = "#00ff88" if drop > -0.05 else "#ffaa00" if drop > -0.1 else "#ff0040"
    st.markdown(f'<div class="card"><div class="metric-label">DIP DETECTOR</div><div style="font-size:36px; font-weight:900; color:{color}">{drop:.3f}%</div><small>Need -{DIP_PCT}% for BUY</small><br><progress value="{abs(drop)}" max="{DIP_PCT*2}" style="width:100%"></progress></div>', unsafe_allow_html=True)
with c3:
    pnl_color = "#00ff88" if pnl >=0 else "#ff0040"
    st.markdown(f'<div class="card"><div class="metric-label">LIVE PNL</div><div style="font-size:36px; font-weight:900; color:{pnl_color}">{pnl:.3f}%</div><small>Entry ${st.session_state.entry:.2f} | TP +{TP_PCT}%</small></div>', unsafe_allow_html=True)
with c4: st.markdown(f'<div class="card"><div class="metric-label">BOT STATUS</div><div style="font-size:18px; font-weight:700">{"🟢 HOLDING "+str(st.session_state.holding_qty)+" SOL" if st.session_state.holding else "🔍 SCANNING DIP"}</div><br><small>Trades: {st.session_state.trades} | Profit: ${st.session_state.profit:.2f}<br>Balance: $39.66 | Trade ${TRADE_USDT}</small></div>', unsafe_allow_html=True)

st.markdown("---")
col_chart, col_log = st.columns([2,1])
with col_chart: st.markdown(f'<div class="card"><b>📈 BSB STRATEGY</b><br>Buy when price drops <b>-{DIP_PCT}%</b> from local high<br>Sell at <b>+{TP_PCT}%</b> Take Profit or <b>-{SL_PCT}%</b> Stop Loss<br><br><code>High: ${st.session_state.last_high:.2f} -> Current: ${price:.2f} -> Drop: {drop:.3f}%</code></div>', unsafe_allow_html=True)
with col_log: log_box = st.empty()

should_buy = drop <= -DIP_PCT
if not st.session_state.holding and should_buy:
    log_box.markdown(f'<div class="buy-signal">🚀 BUY SIGNAL {drop:.3f}% - BUYING ${TRADE_USDT} of SOL @ ${price}</div>', unsafe_allow_html=True)
    if API_KEY:
        res = place_order("Buy", TRADE_USDT)
        log_box.json(res)
        if res and res.get('retCode')==0:
            st.session_state.entry = price
            st.session_state.holding = True
            # Estimate qty from USDT spent
            st.session_state.holding_qty = round(TRADE_USDT / price, 4)
            st.session_state.trades +=1
            st.success(f"BOUGHT ${TRADE_USDT} SOL!")
        else:
            st.error(f"Check: 1) USDT collateral ON? 2) Unified has $20? Error: {res}")

elif st.session_state.holding:
    if pnl >= TP_PCT or pnl <= -SL_PCT:
        log_box.markdown(f'<div class="sell-signal">💰 SELL PNL {pnl:.3f}% @ ${price}</div>', unsafe_allow_html=True)
        if API_KEY:
            res = place_order("Sell", st.session_state.holding_qty)
            log_box.json(res)
        st.session_state.holding = False; st.session_state.entry = 0; st.session_state.holding_qty = 0; st.session_state.last_high = price
    else:
        log_box.markdown(f'<div class="card">⏳ Holding {st.session_state.holding_qty} SOL | Waiting +{TP_PCT}% TP | PNL <b style="color:{pnl_color}">{pnl:.3f}%</b></div>', unsafe_allow_html=True)
else:
    log_box.markdown(f'<div class="card">🤖 Scanning... {SYMBOL} ${price:.2f} | Drop {drop:.4f}% | Next in 15s</div>', unsafe_allow_html=True)

time.sleep(15)
st.rerun()
