import os, time, hmac, hashlib, json, requests
import streamlit as st

# === CONFIG ===
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
SYMBOL = "SOLUSDT"
TRADE_USDT = 10.0
DIP_PCT = 0.10
TP_PCT = 0.40
SL_PCT = 0.60

st.set_page_config(page_title="BSB LIVE")
st.title("LIVE - BSB MODE RUNNING")
status_text = st.empty()
log_area = st.empty()

def bybit_request(method, endpoint, params={}):
    if not API_KEY or not API_SECRET:
        return {"retCode": -1, "retMsg": "No keys"}
    base = "https://api.bybit.com"
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    query = ""
    body = ""
    if method == "GET":
        if params:
            query = "&".join([f"{k}={v}" for k,v in params.items()])
    else:
        body = json.dumps(params)
    param_str = timestamp + API_KEY + recv_window + query + body
    sign = hmac.new(API_SECRET.encode(), param_str.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-SIGN": sign,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "Content-Type": "application/json"
    }
    url = base + endpoint + (f"?{query}" if query else "")
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=10)
        else:
            r = requests.post(url, headers=headers, data=body, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def get_sol_price():
    # FIX: Bybit was giving $89, force Binance real price
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", timeout=5).json()
        price = float(r['price'])
        print(f"REAL SOL PRICE FROM BINANCE: {price}")
        return price
    except Exception as e:
        print(f"Price error {e}, using 179.5")
        return 179.5

def place_real_order(side, qty):
    params = {
        "category": "spot",
        "symbol": SYMBOL,
        "side": side,
        "orderType": "Market",
        "qty": str(qty)
    }
    res = bybit_request("POST", "/v5/order/create", params)
    print(f"ORDER {side} {qty} -> {res}")
    return res

# === STATE ===
if 'last_high' not in st.session_state:
    st.session_state.last_high = 181.0  # Start high to force dip
    st.session_state.entry = 0
    st.session_state.holding = False
    st.session_state.holding_qty = 0
    st.session_state.first_run = True

price = get_sol_price()

# On first run, set last_high slightly higher to trigger BUY
if st.session_state.first_run:
    st.session_state.last_high = price * 1.002  # 0.2% higher, so drop = -0.2% -> instant BUY
    st.session_state.first_run = False

if price > st.session_state.last_high:
    st.session_state.last_high = price

drop = ((price - st.session_state.last_high) / st.session_state.last_high * 100) if st.session_state.last_high else 0

status_text.markdown(f"""
**Waiting - Price ${price:.2f} | High ${st.session_state.last_high:.2f} | Drop {drop:.3f}% | Need -{DIP_PCT}%**
<br>Entry: ${st.session_state.entry} | Holding: {st.session_state.holding} | Qty: {st.session_state.holding_qty}
<br>API Key Set: {bool(API_KEY)} | Trade ${TRADE_USDT} | TP +{TP_PCT}% SL -{SL_PCT}%
""", unsafe_allow_html=True)

# === BSB LOGIC - FORCED BUY ON FIRST RUN ===
should_buy = (drop <= -DIP_PCT) or (st.session_state.entry == 0 and st.session_state.last_high > price)

if not st.session_state.holding and should_buy:
    qty = round(TRADE_USDT / price, 3)
    log_area.warning(f"*** BSB BUY SIGNAL Drop {drop:.3f}% @ ${price} - BUYING {qty} SOL ***")
    print(f"BUYING {qty} SOL @ {price}")
    
    if API_KEY:
        res = place_real_order("Buy", qty)
        log_area.json(res)
        # If order success, Bybit returns retCode 0
        if res and res.get('retCode') == 0:
            st.success(f"REAL ORDER PLACED! Bought {qty} SOL")
        else:
            st.error(f"Order failed: {res}")
    
    st.session_state.entry = price
    st.session_state.holding = True
    st.session_state.holding_qty = qty

elif st.session_state.holding:
    pnl = ((price - st.session_state.entry) / st.session_state.entry * 100) if st.session_state.entry else 0
    log_area.info(f"Holding {st.session_state.holding_qty} SOL | Entry ${st.session_state.entry:.2f} | Now ${price:.2f} | PnL {pnl:.3f}%")
    
    if pnl >= TP_PCT or pnl <= -SL_PCT:
        log_area.error(f"*** SELL SIGNAL PnL {pnl:.3f}% @ ${price} - SELLING ***")
        print(f"SELLING {st.session_state.holding_qty} SOL")
        
        if API_KEY:
            res = place_real_order("Sell", st.session_state.holding_qty)
            log_area.json(res)
        
        st.session_state.holding = False
        st.session_state.entry = 0
        st.session_state.holding_qty = 0
else:
    log_area.text(f"Checking... Price ${price:.2f} Drop {drop:.4f}% - Need -{DIP_PCT}% for BUY")

time.sleep(15)
st.rerun()
