import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go
import os

st.set_page_config(page_title="SOL Live Trader", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

# --- PUT YOUR BYBIT KEYS HERE - REPLACE INSIDE QUOTES ---
API_KEY = "YOUR_BYBIT_KEY_HERE"
API_SECRET = "YOUR_BYBIT_SECRET_HERE"
TRADE_AMOUNT_USDT = 10

def get_data():
    for ex_id in ['bybit', 'okx', 'coinbase']:
        try:
            ex = getattr(ccxt, ex_id)()
            bars = ex.fetch_ohlcv('SOL/USDT', '3m', limit=100)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
            return df
        except:
            continue
    return None

def get_private_client():
    try:
        ex = ccxt.bybit({
            'apiKey': API_KKBFZoeNuooXkay19S,
            'secret': API_wEQBIktBM7WLxfV3TKVbeF1Qn84APFyPQvH4,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        return ex
    except Exception as e:
        st.error(f"Bybit error: {e}")
        return None

df = get_data()
if df is None:
    st.error("Retrying...")
    st.stop()

df['EMA9'] = df['close'].ewm(span=9).mean()
df['EMA21'] = df['close'].ewm(span=21).mean()
last = df.iloc[-1]
signal = "BUY" if last['EMA9'] > last['EMA21'] else "SELL"

st.metric("SOL Price", f"${last['close']:.2f}", signal)

client = get_private_client()
if client:
    try:
        balance = client.fetch_balance()
        usdt_bal = balance.get('USDT', {}).get('free', 0)
        sol_bal = balance.get('SOL', {}).get('free', 0)
        st.success(f"✅ Connected to Bybit | USDT: {usdt_bal:.2f} | SOL: {sol_bal:.4f}")
    except Exception as e:
        st.error(f"Bybit failed: {e}. Check API permissions.")

fig = go.Figure()
fig.add_candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])
fig.add_scatter(x=df['time'], y=df['EMA9'], name="EMA9")
fig.add_scatter(x=df['time'], y=df['EMA21'], name="EMA21")
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader(f"Signal: {signal}")

if client and st.button(f"Execute {signal} NOW - Real Trade"):
    try:
        qty = TRADE_AMOUNT_USDT / last['close']
        if signal == "BUY":
            order = client.create_market_buy_order('SOL/USDT', qty)
        else:
            order = client.create_market_sell_order('SOL/USDT', qty)
        st.success(f"Order placed! {order['id']}")
        st.json(order)
    except Exception as e:
        st.error(f"Order failed: {e}")
