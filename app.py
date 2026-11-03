import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go
import os

st.set_page_config(page_title="SOL Live Trader", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

# --- YOUR BYBIT KEYS - ALREADY FIXED ---
API_KEY = "KKBFZoeNuooXkay19S"
API_SECRET = "wEQBIktBM7WLxfV3TKVbeF1Qn84APFyPQvH4"
TRADE_AMOUNT_USDT = 5  # Changed to 5 so you have enough, you have $39

def get_exchange():
    ex = ccxt.bybit({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    return ex

def get_data():
    try:
        ex = get_exchange()
        bars = ex.fetch_ohlcv('SOL/USDT', '3m', limit=100)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
        return df
    except Exception as e:
        st.error(f"Bybit error: {e}")
        return None

def get_balance():
    try:
        ex = get_exchange()
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {}).get('free', 0)
        return usdt
    except Exception as e:
        return f"Error: {e}"

# --- UI ---
balance = get_balance()
st.write(f"✅ Connected to Bybit | USDT: {balance}")

df = get_data()
if df is not None:
    st.dataframe(df.tail())

if st.button("Execute BUY/SELL NOW"):
    ex = get_exchange()
    try:
        # Example buy
        order = ex.create_market_buy_order('SOL/USDT', TRADE_AMOUNT_USDT)
        st.success(f"BUY Order placed: {order}")
    except Exception as e:
        st.error(f"Trade failed: {e}")
