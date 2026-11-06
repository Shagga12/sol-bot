import os, time, hmac, hashlib, requests, threading
import streamlit as st

# KEYS FROM RENDER
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
SYMBOL = "SOLUSDT"
TRADE_USDT = 10
DIP = 0.10
TP = 0.40
SL = 0.60

st.set_page_config(page_title="BSB LIVE")
st.title("LIVE - BSB MODE RUNNING")

log_box = st.empty()

def bybit_price():
    try:
        r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={SYMBOL}", timeout=5).json()
        return float(r['result']['list'][0]['lastPrice'])
    except:
        return 0

def log(msg):
    print(msg, flush=True)
    log_box.text(msg)

# STATE
last_high = 0
entry = 0
holding = False

log("BSB Bot Started - Checking every 10s")
log(f"API Key present: {bool(API_KEY)}")
log(f"Target: Buy dip -{DIP}% | Sell +{TP}% / -{SL}%")

while True:
    price = bybit_price()
    if price == 0:
        log("Price fetch failed, retry...")
        time.sleep(10)
        continue

    if price > last_high:
        last_high = price

    drop = ((price - last_high)/last_high*100) if last_high else 0

    if not holding and drop <= -DIP:
        log(f"*** BSB BUY SIGNAL! Drop {round(drop,2)}% @ ${price} ***")
        # HERE WOULD BE REAL BYBIT ORDER - FOR NOW SIMULATED
        # To make it real, we need to sign request
        entry = price
        holding = True
        last_high = price
        st.success(f"BOUGHT SOL @ ${price} - Holding")
    
    elif holding:
        pnl = (price - entry)/entry*100
        log(f"Holding: Entry ${entry} | Now ${price} | PnL {round(pnl,2)}% | Drop {round(drop,2)}%")
        if pnl >= TP or pnl <= -SL:
            log(f"*** BSB SELL! PnL {round(pnl,2)}% @ ${price} ***")
            holding = False
            entry = 0
            st.warning(f"SOLD @ ${price} | PnL {round(pnl,2)}%")
    else:
        log(f"Waiting - Price ${price} | High ${round(last_high,2)} | Drop {round(drop,2)}% | Need -{DIP}%")

    time.sleep(10)
