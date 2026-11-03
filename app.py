import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go
import os
import time

st.set_page_config(page_title="SOL Live Trader", layout="wide")
st.title("SOL Bot - 3m TF - LIVE TRADER")

# --- GET API KEYS FROM RENDER ENVIRONMENT ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT", "10")) # $10 per trade default

# --- DATA FETCH (public, no key needed) ---
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

def get_private_client():
    if not API_KEY or not API_SECRET:
        return None
    try:
        ex = ccxt.bybit({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'} # Change to 'future' if you want futures
        })
        return ex
    except Exception as e:
        st.error(f"Bybit client error: {e}")
        return None

df = get_data()

if df is None:
    st.error("All exchanges blocked, retrying...")
    st.stop()

# --- INDICATORS ---
df['EMA9'] = df['close'].ewm(span=9).mean()
df['EMA21'] = df['close'].ewm(span=21).mean()
last = df.iloc[-1]
signal = "BUY" if last['EMA9'] > last['EMA21'] else "SELL"

# --- UI TOP ---
col1, col2, col3 = st.columns(3)
col1.metric("SOL Price", f"${last['close']:.2f}", signal)
col2.metric("EMA9", f"{last['EMA9']:.2f}")
col3.metric("EMA21", f"{last['EMA21']:.2f}")

# --- CHECK BYBIT CONNECTION ---
client = get_private_client()

if not client:
    st.warning("⚠️ BYBIT_API_KEY not set in Render. Bot is in VIEW-ONLY mode. Add keys to trade.")
    st.info("Go to Render -> sol-bot-9999 -> Environment -> Add BYBIT_API_KEY and BYBIT_API_SECRET")
else:
    try:
        balance = client.fetch_balance()
        usdt_bal = balance.get('USDT', {}).get('free', 0)
        sol_bal = balance.get('SOL', {}).get('free', 0)
        st.success(f"✅ Connected to Bybit | USDT: {usdt_bal:.2f} | SOL: {sol_bal:.4f}")
    except Exception as e:
        st.error(f"Bybit connection failed: {e}. Check API permissions (Spot Trade enabled, IP whitelisted).")
        client = None

# --- CHART ---
fig = go.Figure()
fig.add_candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="SOL")
fig.add_scatter(x=df['time'], y=df['EMA9'], name="EMA9")
fig.add_scatter(x=df['time'], y=df['EMA21'], name="EMA21")
st.plotly_chart(fig, use_container_width=True)
st.write(f"Signal: **{signal}**")

# --- TRADING LOGIC ---
st.divider()
st.subheader("Live Trading Control")

auto_trade = st.checkbox("Enable AUTO-TRADING (Real Money)", value=False)
st.caption(f"Will trade ${TRADE_AMOUNT_USDT} per signal on Bybit Spot SOL/USDT")

if client and auto_trade:
    if st.button(f"Execute {signal} NOW"):
        try:
            # Calculate quantity
            price = last['close']
            qty = TRADE_AMOUNT_USDT / price
            
            if signal == "BUY":
                order = client.create_market_buy_order('SOL/USDT', qty)
            else:
                # For SELL, make sure we have SOL
                if sol_bal < qty:
                    qty = sol_bal
                order = client.create_market_sell_order('SOL/USDT', qty)
            
            st.success(f"Order placed! {order['id']}")
            st.json(order)
            # This is when Bybit will show Records Found!
        except Exception as e:
            st.error(f"Order failed: {e}")
    
    # Auto mode (trades every 3 min on signal change - simple example)
    st.info("Auto-trading: If checked, bot will trade on page refresh. Keep this tab open or use Render Cron.")
    
    # Store last signal to avoid re-trading same signal
    if 'last_signal' not in st.session_state:
        st.session_state.last_signal = None
    
    if st.session_state.last_signal != signal:
        st.warning(f"Signal changed from {st.session_state.last_signal} to {signal}. Click Execute to trade.")
        # Uncomment below to make it FULLY automatic (dangerous, use carefully):
        # try:
        #     client.create_market_buy_order('SOL/USDT', qty) if signal=="BUY" else client.create_market_sell_order('SOL/USDT', qty)
        #     st.session_state.last_signal = signal
        # except Exception as e:
        #     st.error(str(e))
else:
    if client:
        st.info("Check 'Enable AUTO-TRADING' and click Execute to place real order on Bybit. After first order, Bybit 'No Records Found' will disappear.")

st.caption("After your first real trade, go to Bybit -> Trade History and you WILL see records.")
