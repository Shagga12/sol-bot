import streamlit as st
import os
import time
import requests
from pybit.unified_trading import HTTP

st.set_page_config(page_title="SOL Bot LIVE AutoTrader", layout="wide", initial_sidebar_state="collapsed")

# --- STYLE ---
st.markdown("""
<style>
.stApp {background:#0e1117; color:white}
.live-box {background:linear-gradient(90deg,#00c853,#009624); color:white; padding:15px; border-radius:10px; text-align:center; font-weight:bold; font-size:20px; margin-bottom:20px}
.metric-card {background:#1e2329; padding:15px; border-radius:10px; text-align:center}
</style>
""", unsafe_allow_html=True)

# --- KEYS ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

if not API_KEY or not API_SECRET:
    st.error("❌ BYBIT_API_KEY / SECRET not set in Render > Environment")
    st.stop()

# Connect Bybit
@st.cache_resource
def get_client():
    return HTTP(api_key=API_KEY, api_secret=API_SECRET, testnet=False)

client = get_client()

def get_price():
    try:
        r = client.get_tickers(category="spot", symbol="SOLUSDT")
        return float(r['result']['list'][0]['lastPrice'])
    except Exception as e:
        # fallback to public price
        try:
            pr = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=5).json()
            return float(pr['result']['list'][0]['lastPrice'])
        except:
            return None

def get_balance():
    try:
        bal = client.get_wallet_balance(accountType="UNIFIED")
        coins = bal['result']['list'][0]['coin']
        usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
        sol = next((c for c in coins if c['coin'] == 'SOL'), None)
        ub = float(usdt['walletBalance']) if usdt else 0
        sb = float(sol['walletBalance']) if sol else 0
        return ub, sb
    except Exception as e:
        st.error(f"Balance error: {e}")
        return 0, 0

def buy_sol(usdt_amount, price):
    try:
        qty = round(usdt_amount / price, 2)
        if qty < 0.01: qty = 0.01
        res = client.place_order(category="spot", symbol="SOLUSDT", side="Buy", orderType="Market", qty=str(qty))
        return res
    except Exception as e:
        return f"BUY FAILED: {e}"

def sell_sol(sol_amount):
    try:
        qty = round(sol_amount, 2)
        if qty < 0.01: return "Too small to sell"
        res = client.place_order(category="spot", symbol="SOLUSDT", side="Sell", orderType="Market", qty=str(qty))
        return res
    except Exception as e:
        return f"SELL FAILED: {e}"

# --- LIVE DATA ---
price = get_price()
usdt_bal, sol_bal = get_balance()

if not price:
    st.error("❌ Can't get SOL price - Bybit blocked. Make sure Render region is Singapore")
    st.stop()

# Header
st.markdown(f'<div class="live-box">LIVE ✅ | SOL ${price} | USDT ${usdt_bal:.2f} | SOL {sol_bal:.4f} | AUTOTRADER ON</div>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("SOL Price", f"${price:.2f}")
c2.metric("USDT", f"${usdt_bal:.2f}")
c3.metric("SOL Held", f"{sol_bal:.4f}")
c4.metric("Total Value", f"${usdt_bal + sol_bal*price:.2f}")

# --- SESSION STATE ---
if 'last_high' not in st.session_state:
    st.session_state.last_high = price
if 'entry' not in st.session_state:
    st.session_state.entry = 0

if price > st.session_state.last_high:
    st.session_state.last_high = price

drop_pct = (st.session_state.last_high - price) / st.session_state.last_high * 100 if st.session_state.last_high else 0

st.divider()
st.write(f"**Last High:** ${st.session_state.last_high:.2f} | **Drop:** {drop_pct:.2f}% | **Entry Price:** ${st.session_state.entry}")

# --- AUTO TRADE ---
st.subheader("🤖 AutoTrader Log")

# SELL
if sol_bal >= 0.02 and st.session_state.entry > 0:
    profit = (price - st.session_state.entry) / st.session_state.entry * 100
    st.info(f"📈 Holding {sol_bal:.3f} SOL | Profit: {profit:.2f}%")
    if profit >= 2.0:
        st.success(f"🎯 TAKE PROFIT {profit:.2f}% - SELLING!")
        res = sell_sol(sol_bal)
        st.write(res)
        st.session_state.entry = 0
        st.balloons()
    elif profit <= -1.5:
        st.error(f"🛑 STOP LOSS {profit:.2f}% - SELLING!")
        res = sell_sol(sol_bal)
        st.write(res)
        st.session_state.entry = 0

# BUY
elif usdt_bal >= 6 and drop_pct >= 1.5:
    buy_amt = 10.0
    if usdt_bal < 10:
        buy_amt = usdt_bal - 1  # leave $1
    st.warning(f"🔥 DIP {drop_pct:.2f}% DETECTED - BUYING ${buy_amt} SOL @ ${price}")
    res = buy_sol(buy_amt, price)
    st.write(res)
    # If buy succeeded, save entry
    if isinstance(res, dict) and res.get('result'):
        st.session_state.entry = price
        st.session_state.last_high = price
        st.success("✅ BOUGHT!")
    else:
        st.error(f"Buy error: {res}")
else:
    st.info(f"⏳ Waiting for dip... Need 1.5% drop, now {drop_pct:.2f}% | Need $6 USDT to buy")

st.caption("Strategy: 3m Dip Buy $10 | TP +2% | SL -1.5% | Real Money | Refreshes every 60s")
st.progress(min(drop_pct/1.5, 1.0), text=f"Dip progress to buy signal: {drop_pct:.2f}% / 1.5%")

# Auto refresh
time.sleep(60)
st.rerun()
