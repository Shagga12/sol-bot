import streamlit as st
import ccxt, pandas as pd

st.title("SOL Bot - 3m TF")
exchange = ccxt.binance()

@st.cache_data(ttl=60)
def get_data():
    bars = exchange.fetch_ohlcv('SOL/USDT', '3m', limit=100)
    df = pd.DataFrame(bars, columns=['t','o','h','l','c','v'])
    df['EMA9'] = df['c'].ewm(span=9).mean()
    df['EMA21'] = df['c'].ewm(span=21).mean()
    return df

df = get_data()
last = df.iloc[-1]
signal = "BUY" if last['EMA9'] > last['EMA21'] else "SELL"
st.metric("SOL Price", f"${last['c']:.2f}", signal)
st.line_chart(df[['c','EMA9','EMA21']])
st.success(f"Signal: {signal}")
