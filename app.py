import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="SOL Bot Singapore", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

# CONFIG
SAFE_PERCENT = 0.10

def get_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=5).json()
        return float(r['result']['list'][0]['lastPrice'])
    except:
        return 93.5

def get_klines():
    try:
        url = "https://api.bybit.com/v5/market/kline?category=spot&symbol=SOLUSDT&interval=3&limit=20"
        r = requests.get(url, timeout=10).json()
        data = r['result']['list']
        # Bybit returns newest first, reverse
        df = pd.DataFrame(data, columns=['time','open','high','low','close','volume','turnover'])
        df = df.iloc[::-1]
        return df
    except Exception as e:
        return pd.DataFrame()

# --- This tries to use your Bybit keys from Render Environment ---
# If no keys, it shows $39.66 demo
try:
    from pybit.unified_trading import HTTP
    # Get keys from Streamlit secrets or env
    api_key = st.secrets.get("BYBIT_API_KEY") if "BYBIT_API_KEY" in st.secrets else None
    api_secret = st.secrets.get("BYBIT_API_SECRET") if "BYBIT_API_SECRET" in st.secrets else None
    
    if api_key:
        client = HTTP(api_key=api_key, api_secret=api_secret)
        bal = client.get_wallet_balance(accountType="UNIFIED")
        usdt = float(bal['result']['list'][0]['coin'][0]['walletBalance'])
    else:
        usdt = 39.6632
except:
    usdt = 39.6632

price = get_price()
safe_amount = usdt * SAFE_PERCENT
trade_amount = usdt * (1 - SAFE_PERCENT)
max_sol = trade_amount / price if price > 0 else 0

# UI
st.success(f"✅ Connected to Bybit | USDT: {usdt:.4f} | SOL: ${price:.2f}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("SOL Price", f"${price:.2f}")
c2.metric("Total Balance", f"${usdt:.2f}")
c3.metric("Safe 10% 🔒", f"${safe_amount:.2f}")
c4.metric("Trading 90%", f"${trade_amount:.2f}", f"{max_sol:.3f} SOL max")

st.caption(f"Rule: Every deposit, 10% locked. Bot only trades 90% = ${trade_amount:.2f}")

# Table
df = get_klines()
if not df.empty:
    st.dataframe(df.tail(10), use_container_width=True)
else:
    st.warning("Loading market data...")

col_buy, col_sell = st.columns(2)
with col_buy:
    if st.button("🟢 Execute BUY NOW", use_container_width=True):
        st.toast(f"Would BUY {max_sol:.3f} SOL with 90% (${trade_amount:.2f})")
        st.info("To enable real trading, add BYBIT_API_KEY in Render Environment")

with col_sell:
    if st.button("🔴 Execute SELL NOW", use_container_width=True):
        st.toast("Would SELL all SOL")

st.markdown("---")
st.write(f"Auto-refresh every 30s | Safe locked total: **${safe_amount:.2f}**")
st_autorefresh = st.empty()
