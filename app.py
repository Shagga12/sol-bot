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
