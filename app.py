
import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go

st.title("SOL Bot - 3m TF")

def get_data():
    for ex_id in ['bybit', 'okx', 'coinbase', 'kucoin']:
        try:
            ex = getattr(ccxt, ex_id)()
            bars = ex.fetch_ohlcv('SOL/USDT', '3m', limit=100)
            df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume'])
            return df
        except:
            continue
    return None

df = get_data()

if df is None:
    st.error("All exchanges blocked, retrying...")
    st.stop()

df['EMA9'] = df['close'].ewm(span=9).mean()
df['EMA21'] = df['close'].ewm(span=21).mean()

last = df.iloc[-1]
signal = "BUY" if last['EMA9'] > last['EMA21'] else "SELL"

st.metric("SOL Price", f"${last['close']:.2f}", signal)

fig = go.Figure()
fig.add_candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="SOL")
fig.add_scatter(x=df['time'], y=df['EMA9'], name="EMA9")
fig.add_scatter(x=df['time'], y=df['EMA21'], name="EMA21")
st.plotly_chart(fig, use_container_width=True)

st.write(f"Signal: {signal}")
