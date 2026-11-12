import hmac
import os
import streamlit as st
from diagnostics import ConnectionError, price, account_check

st.set_page_config(page_title='SOL Bot · Connection Check', layout='wide')
st.title('SOL Bot · Connection Check')
st.warning('DIAGNOSTIC MODE — real trading is disabled. This build cannot place orders.')
st.caption('No fabricated prices, balances, P&L, or trade confirmations are shown.')
if st.button('Check current SOL/USDT spot price'):
    try:
        st.metric('Bybit SOL/USDT', '$%.4f' % price())
    except ConnectionError as error:
        st.error(str(error))

password = os.getenv('BOT_DASHBOARD_PASSWORD', '')
if not password:
    st.info('Private account diagnostics require BOT_DASHBOARD_PASSWORD in Render secrets. Do not enter secrets in chat or source code.')
    st.stop()
entered = st.text_input('Dashboard password', type='password')
if not hmac.compare_digest(entered.encode(), password.encode()):
    st.info('Enter the dashboard password to access account diagnostics.')
    st.stop()
if st.button('Verify read-only Bybit connection'):
    try:
        result = account_check(os.getenv('BYBIT_API_KEY'), os.getenv('BYBIT_API_SECRET'))
        st.success('Bybit accepted the read-only key and account-balance request.')
        for account in result.get('list', []):
            for coin in account.get('coin', []):
                st.write({'asset': coin.get('coin'), 'wallet balance': coin.get('walletBalance')})
    except ConnectionError as error:
        st.error(str(error))
st.caption('Missing credentials or failed API calls stop the check. No live-trading switch exists in this build.')


st.divider()
st.subheader('Verify a Bybit spot order')
st.caption('Read-only lookup by client order ID. This does not place, repeat, or cancel an order.')
with st.form('order_receipt'):
    symbol = st.selectbox('Trading pair', ['BTCUSDT', 'SOLUSDT', 'ETHUSDT', 'BNBUSDT'])
    client_id = st.text_input('Client order ID (orderLinkId)', max_chars=36)
    days = st.number_input('Look back in days (maximum 7)', min_value=1, max_value=7, value=7)
    submitted = st.form_submit_button('Check execution evidence')
if submitted:
    import time
    from order_reconciliation import reconcile, ReceiptJournal
    try:
        key, secret = os.getenv('BYBIT_API_KEY'), os.getenv('BYBIT_API_SECRET')
        account_check(key, secret)
        end = int(time.time() * 1000)
        receipt = reconcile(symbol, client_id.strip(), key, secret,
                            start_ms=end-int(days)*86400000, end_ms=end)
        st.json(receipt)
        journal_path = os.getenv('BOT_RECEIPT_DB')
        if journal_path:
            journal = ReceiptJournal(journal_path)
            try:
                journal.save(receipt)
            finally:
                journal.close()
            st.caption('Receipt saved. Persistent cloud storage must be configured for restart durability.')
        else:
            st.info('Receipt displayed only. BOT_RECEIPT_DB is not configured; nothing was saved to disk.')
        if receipt['final']:
            st.success('Final order status and execution totals agree.')
        else:
            st.warning('Outcome is unresolved or still open. Do not interpret this as permission to submit another order.')
    except (ConnectionError, ValueError) as error:
        st.error(str(error))
    except Exception:
        st.error('Receipt check or storage failed. No order was placed; outcome remains unverified.')
