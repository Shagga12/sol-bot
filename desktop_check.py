"""Bybit diagnostics. GET requests only; no trading or transfer methods."""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

class ConnectionError(Exception):
    pass

def get(endpoint, params=None, key=None, secret=None):
    allowed = {'/v5/market/tickers', '/v5/user/query-api', '/v5/account/wallet-balance'}
    if endpoint not in allowed:
        raise ConnectionError('Unsupported diagnostic endpoint.')
    query = urllib.parse.urlencode(params or {})
    headers = {'Accept': 'application/json'}
    if key or secret:
        if not key or not secret:
            raise ConnectionError('Both Bybit credential settings are required.')
        stamp = str(int(time.time() * 1000))
        signature = hmac.new(secret.encode(), (stamp + key + '5000' + query).encode(), hashlib.sha256).hexdigest()
        headers.update({'X-BAPI-API-KEY': key, 'X-BAPI-TIMESTAMP': stamp,
                        'X-BAPI-RECV-WINDOW': '5000', 'X-BAPI-SIGN': signature})
    request = urllib.request.Request('https://api.bybit.com' + endpoint + ('?' + query if query else ''), headers=headers, method='GET')
    # Never forward signed headers to another URL.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        raise ConnectionError('Bybit returned HTTP %s. Check account and server eligibility.' % error.code) from None
    except Exception:
        raise ConnectionError('Bybit did not return a valid response. No substitute data is displayed.') from None
    if body.get('retCode') != 0:
        raise ConnectionError('Bybit rejected the request (code %s). Check key permissions, expiry and IP restrictions.' % body.get('retCode'))
    return body.get('result', {})

def price():
    result = get('/v5/market/tickers', {'category': 'spot', 'symbol': 'SOLUSDT'})
    try:
        value = float(result['list'][0]['lastPrice'])
        if value <= 0:
            raise ValueError()
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        raise ConnectionError('Bybit returned no valid SOL price.') from None

def account_check(key, secret):
    if not key or not secret:
        raise ConnectionError('Bybit credentials are not configured. Add a separate read-only key in Render secrets.')
    info = get('/v5/user/query-api', key=key, secret=secret)
    if info.get('readOnly') != 1:
        raise ConnectionError('Use a separate read-only API key for this diagnostic build.')
    return get('/v5/account/wallet-balance', {'accountType': 'UNIFIED', 'coin': 'USDT,SOL'}, key, secret)


def desktop_check():
    import tkinter as tk
    from tkinter import simpledialog, messagebox
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    try:
        key = simpledialog.askstring('Capital Connect — account check', 'Paste your Bybit API KEY:', show='*', parent=root)
        if not key:
            return
        secret = simpledialog.askstring('Capital Connect — account check', 'Paste the matching API SECRET:', show='*', parent=root)
        if not secret:
            return
        result = account_check(key.strip(), secret.strip())
        coins = [coin for account in result.get('list', []) for coin in account.get('coin', [])]
        usdt = next((coin for coin in coins if coin.get('coin') == 'USDT'), None)
        text = 'Read-only account connection: verified\nAccount: Unified Trading\n'
        if usdt is None:
            text += 'No USDT entry was returned.'
        else:
            for label, field in [('Wallet balance', 'walletBalance'), ('Equity', 'equity'), ('Locked in spot orders', 'locked'), ('Spot borrowing', 'spotBorrow')]:
                text += label + ': ' + str(usdt.get(field, 'Not returned')) + ' USDT\n'
        text += '\nThis program cannot place orders or transfer funds.\nCredentials are not saved to a file.'
        messagebox.showinfo('Capital Connect — result', text, parent=root)
    except ConnectionError as error:
        messagebox.showerror('Connection check stopped', str(error), parent=root)
    except Exception:
        messagebox.showerror('Connection check stopped', 'The check could not complete. No order or transfer was sent.', parent=root)
    finally:
        root.destroy()

if __name__ == '__main__':
    desktop_check()
