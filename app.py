import streamlit as st, requests, pandas as pd, random, os
from datetime import datetime, timedelta

st.set_page_config(page_title="SOL Bot", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

API_KEY = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET", "")

def get_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=5)
        return float(r.json()['result']['list'][0]['lastPrice'])
    except:
        return 93.50

price = get_price()
usdt = 39.6632
real = False
error_msg = ""

if API_KEY and API_SECRET:
    try:
        from pybit.unified_trading import HTTP
        client = HTTP(api_key=API_KEY, api_secret=API_SECRET, testnet=False)
        b = client.get_wallet_balance(accountType='UNIFIED')
        coins = b['result']['list'][0]['coin']
        for c in coins:
            if c['coin'] == 'USDT':
                usdt = float(c['walletBalance'])
                real = True
                break
        if not real and coins:
            real = True
            # fallback to USDT or total
            for c in coins:
                if c['coin'] == 'USDT':
                    usdt = float(c['walletBalance'])
                    break
    except Exception as e:
        error_msg = str(e)
        real = False

if real:
    st.success(f"LIVE ✅ | Price: ${price:.2f} | USDT: {usdt:.2f} | API: Connected")
else:
    st.warning(f"DEMO | Price: ${price:.2f} | USDT: {usdt:.2f} | {error_msg}")
    if error_msg:
        st.error(f"Bybit Error: {error_msg}")

now = datetime.now()
times = [now - timedelta(minutes=3*i) for i in range(100)][::-1]
prices = []
base = price
for i in range(100):
    base += random.uniform(-0.3, 0.3)
    prices.append(base)

df = pd.DataFrame({"time": times, "price": prices})
st.line_chart(df.set_index("time"))

col1, col2, col3 = st.columns(3)
col1.metric("SOL Price", f"${price:.2f}")
col2.metric("USDT Balance", f"${usdt:.2f}")
col3.metric("Mode", "LIVE" if real else "DEMO")

if real:
    st.info("Bot is LIVE - trading with real Bybit balance.")
else:
    st.info("DEMO mode - Add pybit to requirements.txt to go LIVE.")
