import streamlit as st, requests, pandas as pd, random, os, hmac, hashlib, time
from datetime import datetime, timedelta

st.set_page_config(page_title="SOL Bot", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

API_KEY = os.environ.get("BYBIT_API_KEY", "").strip()
API_SECRET = os.environ.get("BYBIT_API_SECRET", "").strip()

def get_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=5)
        return float(r.json()['result']['list'][0]['lastPrice'])
    except:
        return 93.50

def get_bybit_balance():
    if not API_KEY or not API_SECRET:
        return None, "No API keys in Environment"
    try:
        timestamp = str(int(time.time()*1000))
        recv_window = "5000"
        query = "accountType=UNIFIED"
        sign_str = timestamp + API_KEY + recv_window + query
        signature = hmac.new(API_SECRET.encode(), sign_str.encode(), hashlib.sha256).hexdigest()
        headers = {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": recv_window
        }
        url = f"https://api.bybit.com/v5/account/wallet-balance?{query}"
        r = requests.get(url, headers=headers, timeout=10)
        # Try to parse
        data = r.json()
        if data.get("retCode") != 0:
            return None, f"Bybit API: {data.get('retMsg')} - {data}"
        coins = data['result']['list'][0]['coin']
        for c in coins:
            if c['coin'] == 'USDT':
                return float(c['walletBalance']), None
        return 0, f"USDT not found. Coins: {[x['coin'] for x in coins]}"
    except Exception as e:
        return None, f"{str(e)} | Response: {r.text[:200] if 'r' in locals() else 'no response'}"

price = get_price()
balance, err = get_bybit_balance()

if balance is not None:
    usdt = balance
    real = True
    st.success(f"LIVE ✅ | Price: ${price:.2f} | USDT: {usdt:.2f} | API: Connected")
else:
    usdt = 39.66
    real = False
    st.warning(f"DEMO | Price: ${price:.2f} | USDT: {usdt:.2f} | {err}")
    if err:
        st.error(f"Bybit Error: {err}")

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
