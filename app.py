import streamlit as st
import os
import time
import hmac
import hashlib
import requests
import json

st.set_page_config(page_title="SOL Bot LIVE AutoTrader", layout="wide")

st.markdown("""
<style>
.stApp {background:#0e1117; color:white}
.live-box {background:#00c853; color:white; padding:15px; border-radius:10px; text-align:center; font-weight:bold; font-size:20px}
</style>
""", unsafe_allow_html=True)

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

if not API_KEY or not API_SECRET:
    st.error("❌ Set BYBIT_API_KEY and BYBIT_API_SECRET in Render > Environment")
    st.stop()

def get_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=10).json()
        return float(r['result']['list'][0]['lastPrice'])
    except:
        return None

def bybit_request(method, endpoint, params=""):
    timestamp = str(int(time.time()*1000))
    recv_window = "5000"
    to_sign = timestamp + API_KEY + recv_window + params if method=="GET" else timestamp + API_KEY + recv_window + params
    signature = hmac.new(API_SECRET.encode(), to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": signature,
        "Content-Type": "application/json"
    }
    url = f"https://api.bybit.com{endpoint}"
    if method=="GET":
        if params: url += "?" + params
        return requests.get(url, headers=headers, timeout=10).json()
    else:
        return requests.post(url, headers=headers, data=params, timeout=10).json()

def get_balance():
    try:
        res = bybit_request("GET", "/v5/account/wallet-balance", "accountType=UNIFIED")
        coins = res['result']['list'][0]['coin']
        usdt = next((c for c in coins if c['coin']=='USDT'), None)
        sol = next((c for c in coins if c['coin']=='SOL'), None)
        return float(usdt['walletBalance']) if usdt else 0, float(sol['walletBalance']) if sol else 0, res
    except Exception as e:
        return 0, 0, str(e)

def place_order(side, qty):
    try:
        body = json.dumps({"category":"spot","symbol":"SOLUSDT","side":side,"orderType":"Market","qty":str(qty)})
        ts = str(int(time.time()*1000))
        sign_str = ts + API_KEY + "5000" + body
        sig = hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
        headers = {"X-BAPI-API-KEY":API_KEY,"X-BAPI-TIMESTAMP":ts,"X-BAPI-RECV-WINDOW":"5000","X-BAPI-SIGN":sig,"Content-Type":"application/json"}
        r = requests.post("https://api.bybit.com/v5/order/create", headers=headers, data=body, timeout=10).json()
        return r
    except Exception as e:
        return str(e)

# --- UI ---
price = get_price()
usdt_bal, sol_bal, raw = get_balance()

if not price:
    st.error("Can't get price")
    st.stop()

st.markdown(f'<div class="live-box">LIVE ✅ | SOL ${price:.2f} | USDT ${usdt_bal:.2f} | SOL {sol_bal:.4f} | AUTOTRADER ON - NO PYBIT</div>', unsafe_allow_html=True)

c1,c2,c3,c4 = st.columns(4)
c1.metric("SOL", f"${price:.2f}")
c2.metric("USDT", f"${usdt_bal:.2f}")
c3.metric("SOL Held", f"{sol_bal:.4f}")
c4.metric("Total", f"${usdt_bal + sol_bal*price:.2f}")

if 'last_high' not in st.session_state: st.session_state.last_high = price
if 'entry' not in st.session_state: st.session_state.entry = 0
if price > st.session_state.last_high: st.session_state.last_high = price

drop_pct = (st.session_state.last_high - price)/st.session_state.last_high*100

st.divider()
st.write(f"Last High: ${st.session_state.last_high:.2f} | Drop: {drop_pct:.2f}% | Entry: {st.session_state.entry}")

st.subheader("🤖 AutoTrader")

# SELL
if sol_bal >= 0.02 and st.session_state.entry > 0:
    profit = (price - st.session_state.entry)/st.session_state.entry*100
    st.info(f"Holding {sol_bal:.3f} SOL | Profit {profit:.2f}%")
    if profit >= 2.0 or profit <= -1.5:
        st.warning(f"{'TAKE PROFIT' if profit>0 else 'STOP LOSS'} {profit:.2f}% - SELLING {sol_bal}")
        res = place_order("Sell", round(sol_bal,2))
        st.json(res)
        if res.get('retCode')==0: st.session_state.entry=0

# BUY
elif usdt_bal >= 6 and drop_pct >= 1.5:
    buy_amt = min(10, usdt_bal-1)
    qty = round(buy_amt/price, 2)
    if qty < 0.01: qty = 0.01
    st.warning(f"🔥 DIP {drop_pct:.2f}% - BUYING {qty} SOL (~${buy_amt})")
    res = place_order("Buy", qty)
    st.json(res)
    if res.get('retCode')==0:
        st.session_state.entry = price
        st.session_state.last_high = price
        st.success("✅ BOUGHT!")
else:
    st.info(f"⏳ Waiting - Need 1.5% dip, now {drop_pct:.2f}%")

st.caption("Uses $10 per trade | TP +2% | SL -1.5% | Auto refresh 60s")
st.write("Raw balance response:", raw)

time.sleep(60)
st.rerun()
