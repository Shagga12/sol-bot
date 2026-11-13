"""Manual-trading connection diagnostics. GET requests only; no orders or activation."""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ALLOWED = {'/v5/user/query-api', '/v5/account/wallet-balance'}

def read(endpoint, key, secret, params=None):
    if endpoint not in ALLOWED:
        raise ValueError('Only approved read-only diagnostics are allowed')
    query = urlencode(params or {})
    timestamp = str(int(time.time() * 1000))
    signature = hmac.new(secret.encode(), (timestamp + key + '5000' + query).encode(), hashlib.sha256).hexdigest()
    request = Request('https://api.bybit.com' + endpoint + ('?' + query if query else ''),
                      headers={'X-BAPI-API-KEY': key, 'X-BAPI-SIGN': signature,
                               'X-BAPI-TIMESTAMP': timestamp, 'X-BAPI-RECV-WINDOW': '5000'}, method='GET')
    # Reject redirects so signed headers cannot reach a different host.
    from urllib.request import HTTPRedirectHandler, build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with build_opener(NoRedirect).open(request, timeout=10) as response:
        body = json.load(response)
    if body.get('retCode') != 0:
        raise RuntimeError('Bybit rejected the diagnostic request; code=' + str(body.get('retCode')))
    if not isinstance(body.get('result'), dict):
        raise RuntimeError('Unexpected diagnostic response')
    return body['result']

def summarize(info, wallet):
    accounts = wallet.get('list', [])
    unified = next((a for a in accounts if a.get('accountType') == 'UNIFIED'), None)
    coin = next((c for c in (unified or {}).get('coin', []) if c.get('coin') == 'USDT'), None)
    return {'mode': 'MANUAL_SETUP', 'automatic_real_orders': False,
            'connection_verified': True, 'unified_wallet_returned': unified is not None,
            'key_access': {0: 'read_write', 1: 'read_only'}.get(info.get('readOnly'), 'unknown'),
            'spot_permission_present': 'SpotTrade' in info.get('permissions', {}).get('Spot', []),
            'withdraw_permission_present': 'Withdraw' in info.get('permissions', {}).get('Wallet', []),
            'reported_usdt_wallet_balance': (coin or {}).get('walletBalance'),
            'reported_usdt_locked': (coin or {}).get('locked'),
            'balance_note': 'Wallet balance is not a verified spendable spot amount. Check Available in Bybit before submitting your trade.',
            'activation_ready': False,
            'remaining': ['Connect dashboard to this worker', 'Verify current spot minimum size and available funds',
                          'Review demo results', 'User places and confirms trades in Bybit']}

def main():
    key, secret = os.getenv('BYBIT_API_KEY'), os.getenv('BYBIT_API_SECRET')
    if not key or not secret:
        print(json.dumps({'connection_verified': False, 'reason': 'credentials_not_configured', 'automatic_real_orders': False}))
        return 1
    try:
        info = read('/v5/user/query-api', key, secret)
        wallet = read('/v5/account/wallet-balance', key, secret, {'accountType': 'UNIFIED', 'coin': 'USDT'})
        print(json.dumps(summarize(info, wallet), indent=2))
        return 0
    except Exception as error:
        # Never echo a response body, request headers, key or secret.
        print(json.dumps({'connection_verified': False, 'reason': type(error).__name__, 'automatic_real_orders': False}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
