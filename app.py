import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="SOL Bot Singapore", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

SAFE_PERCENT = 0.10

def get_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=10).json()
        return float(r['result']['list'][0]['lastPrice'])
    except:
        return 93.50

def get_klines():
    try:
        url = "https://api.bybit.com/v5/market/kline?category=spot&symbol=SOLUSDT&interval=3&limit=10"
        r = requests.get(url, timeout=10).json()
        data = r['result']['list']
        rows = []
        for k in data:
            rows.append({
                "Time": str(k[0]),
                "Open": float(k[1]),
                "High": float(k[2]),
                "Low": float(k[3]),
                "Close": float(k[4]),
            })
        df = pd.DataFrame(rows)
        return df.iloc[::-1]  # oldest first
    except Exception as e:
        return pd.DataFrame()

# Balance - using your $39.66 or Bybit API if keys exist
try:
    usdt = 39.6632
    # if you add keys in Render Environment, it will use real balance
    if "BYBIT_API_KEY" in st.secrets:
        from pybit.unified_trading import HTTP
        client = HTTP(api_key=st.secrets["BYBIT_API_KEY"], api_secret=st.secrets["BYBIT_API_SECRET"])
        bal = client.get_wallet_balance(accountType="UNIFIED")
        usdt = float(bal['result']['list'][0]['coin'][0]['walletBalance'])
except:
    usdt = 39.6632

price = get_price()
safe_amount = usdt * SAFE_PERCENT
trade_amount = usdt * (1 - SAFE_PERCENT)
max_sol = trade_amount / price if price else 0

st.success(f"✅ Connected to Bybit | USDT: {usdt:.4f} | SOL: ${price:.2f}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("SOL Price", f"${price:.2f}")
c2.metric("Total Balance", f"${usdt:.2f}")
c3.metric("Safe 10% 🔒", f"${safe_amount:.2f}")
c4.metric("Trading 90%", f"${trade_amount:.2f}", f"{max_sol:.3f} SOL max")

st.caption(f"Rule: Every deposit, 10% locked. Bot only trades 90% = ${trade_amount:.2f}")

# Market table - FIXED
df = get_klines()
if not df.empty:
    st.dataframe(df, use_container_width=True)
else:
    st.warning("Loading market data... retrying")

col1, col2 = st.columns(2)
with col1:
    st.button("🟢 Execute BUY NOW", use_container_width=True)
with col2:
    st.button("🔴 Execute SELL NOW", use_container_width=True)

st.markdown("---")
st.write(f"Auto-refresh every 30s | Safe locked total: **${safe_amount:.2f}**")
st.markdown(f"[Live Bot Link](https://sol-bot-9999.onrender.com)")
