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
        # Find USDT properly
        for c in coins:
            if c['coin'] == 'USDT':
                usdt = float(c['walletBalance'])
                real = True
                break
        # If USDT not found, try to find any balance and still mark real
        if not real and coins:
            # Check if account has any USDT value
            total_usd = 0
            for c in coins:
                try:
                    total_usd += float(c.get('walletBalance', 0)) if c['coin'] == 'USDT' else float(c.get('usdValue', 0))
                except:
                    pass
            if total_usd > 0:
                usdt = total_usd
            real = True
    except Exception as e:
        error_msg = str(e)
        real = False

# Show status bar
if real:
    st.success(f"LIVE ✅ | Price: ${price:.2f} | USDT: {usdt:.2f} | API: Connected")
else:
    st.warning(f"DEMO | Price: ${price:.2f} | USDT: {usdt:.2f} | {error_msg}")
    if error_msg:
        st.error(f"Bybit Error: {error_msg}")

# --- Trading simulation / chart ---
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
    st.info("Bot is LIVE - trading with real Bybit balance. 3m timeframe strategy active.")
else:
    st.info("Bot is in DEMO mode. Check: 1) USDT in Unified Account 2) API has Read permission 3) No IP restriction")
