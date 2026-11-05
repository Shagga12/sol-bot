import streamlit as st
import os
import time
from pybit.unified_trading import HTTP
import pandas as pd

st.set_page_config(page_title="SOL Bot LIVE AutoTrader", layout="wide")

# --- API ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

st.markdown("""
<style>
.stApp {background:#0e1117; color:white}
.live {background:#00c853; color:white; padding:10px; border-radius:8px; text-align:center; font-weight:bold; font-size:18px}
</style>
""", unsafe_allow_html=True)

if not API_KEY or not API_SECRET:
    st.error("❌ BYBIT_API_KEY / SECRET not set in Render")
    st.stop()

client = HTTP(api_key=API_KEY, api_secret=API_SECRET, testnet=False)

# --- Functions ---
def get_price():
    try:
        ticker = client.get_tickers(category="spot", symbol="SOLUSDT")
        return float(ticker['result']['list'][0]['lastPrice'])
    except Exception as e:
        return None

def get_balance():
    try:
        bal = client.get_wallet_balance(accountType="UNIFIED")
        coins = bal['result']['list'][0]['coin']
        usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
        sol = next((c for c in coins if c['coin'] == 'SOL'), None)
        return float(usdt['walletBalance']) if usdt else 0, float(sol['walletBalance']) if sol else 0
    except Exception as e:
        return 0, 0

def place_buy(usdt_amount, price):
    try:
        qty = round(usdt_amount / price, 3)  # SOL qty
        if qty < 0.01: qty = 0.01
        order = client.place_order(category="spot", symbol="SOLUSDT", side="Buy", orderType="Market", qty=str(qty))
        return order
    except Exception as e:
        return str(e)

def place_sell(sol_amount):
    try:
        qty = round(sol_amount, 3)
        if qty < 0.01: return "too small"
        order = client.place_order(category="spot", symbol="SOLUSDT", side="Sell", orderType="Market", qty=str(qty))
        return order
    except Exception as e:
        return str(e)

# --- UI ---
price = get_price()
usdt_bal, sol_bal = get_balance()

if price:
    st.markdown(f'<div class="live">LIVE ✅ | Price: ${price} | USDT: ${usdt_bal:.2f} | SOL: {sol_bal:.4f} | AutoTrader ON</div>', unsafe_allow_html=True)
else:
    st.error("Cannot get price - Bybit blocked? Check Singapore region")
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("SOL Price", f"${price}")
col2.metric("USDT Balance", f"${usdt_bal:.2f}")
col3.metric("SOL Balance", f"{sol_bal:.4f}")
col4.metric("Mode", "AUTO LIVE")

# --- AUTO TRADE LOGIC (3m Dip Buy) ---
# Strategy: If price drops 1.5% from last high, buy $10. Sell at +2% profit

if 'last_high' not in st.session_state:
    st.session_state.last_high = price
if 'entry_price' not in st.session_state:
    st.session_state.entry_price = 0

if price > st.session_state.last_high:
    st.session_state.last_high = price

drop_pct = (st.session_state.last_high - price) / st.session_state.last_high * 100

st.write(f"Last High: ${st.session_state.last_high:.2f} | Current Drop: {drop_pct:.2f}% | Entry: ${st.session_state.entry_price}")

# SELL LOGIC
if sol_bal > 0.01 and st.session_state.entry_price > 0:
    profit_pct = (price - st.session_state.entry_price) / st.session_state.entry_price * 100
    st.write(f"📈 Holding SOL - Profit: {profit_pct:.2f}%")
    if profit_pct >= 2.0:  # Take profit 2%
        st.warning(f"SELLING - Profit {profit_pct:.2f}%")
        res = place_sell(sol_bal)
        st.write(res)
        st.session_state.entry_price = 0
    elif profit_pct <= -1.5:  # Stop loss -1.5%
        st.error(f"STOP LOSS - {profit_pct:.2f}%")
        res = place_sell(sol_bal)
        st.write(res)
        st.session_state.entry_price = 0

# BUY LOGIC
elif usdt_bal > 5 and drop_pct >= 1.5:  # Buy dip 1.5%
    buy_usdt = min(10, usdt_bal)  # Use $10 per trade, safe
    st.success(f"BUY SIGNAL - Dip {drop_pct:.2f}% - Buying ${buy_usdt} SOL")
    res = place_buy(buy_usdt, price)
    st.write(res)
    if isinstance(res, dict):
        st.session_state.entry_price = price
        st.session_state.last_high = price
else:
    st.info(f"Waiting - Need 1.5% dip to buy. Current dip only {drop_pct:.2f}%")

st.caption("AutoTrader checks every refresh. Render auto-refreshes every 3m. Uses $10 per trade, 2% TP, -1.5% SL. Real money!")

# Auto refresh every 60 sec
time.sleep(60)
st.rerun()
