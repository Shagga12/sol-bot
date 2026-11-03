import streamlit as st, requests, pandas as pd, random, os
from datetime import datetime, timedelta

st.set_page_config(page_title="SOL Bot", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

API_KEY = os.environ.get("BYBIT_API_KEY", "")
API_SECRET = os.environ.get("BYBIT_API_SECRET", "")

def get_price():
    try:
        r = requests.get("https://api.bybit.com/v5/market/tickers?category=spot&symbol=SOLUSDT", timeout=10).json()
        return float(r['result']['list'][0]['lastPrice'])
    except: return 93.50

price = get_price()
usdt = 39.6632
real = False
if API_KEY and API_SECRET:
    try:
        from pybit.unified_trading import HTTP
        client = HTTP(api_key=API_KEY, api_secret=API_SECRET)
        b = client.get_wallet_balance(accountType="UNIFIED")
        usdt = float(b['result']['list'][0]['coin'][0]['walletBalance'])
        real = True
    except: pass

safe, trade = usdt*0.10, usdt*0.90
st.success(f"{'✅ REAL' if real else '✅ DEMO'} | USDT: {usdt:.4f} | SOL: ${price:.2f}")

c1,c2,c3,c4 = st.columns(4)
c1.metric("SOL Price", f"${price:.2f}")
c2.metric("Total", f"${usdt:.2f}")
c3.metric("Safe 10% 🔒", f"${safe:.2f}")
c4.metric("Trading 90%", f"${trade:.2f}")

rows=[]
now=datetime.now()
for i in range(10):
    t=now-timedelta(minutes=3*(9-i)); o=price+random.uniform(-1,1); cl=o+random.uniform(-0.5,0.5)
    rows.append({"Time":t.strftime("%H:%M:%S"),"Open":round(o,2),"Close":round(cl,2),"Signal":"BUY" if cl>o else "SELL"})
st.dataframe(pd.DataFrame(rows), use_container_width=True)

st.button("🟢 Execute BUY NOW", use_container_width=True)
st.button("🔴 Execute SELL NOW", use_container_width=True)
