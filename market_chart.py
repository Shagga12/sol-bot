"""Cached public BTC spot candles. No API keys or order routes."""
import json
import time
import threading
from urllib.request import Request, build_opener, HTTPRedirectHandler
from decimal import Decimal

_lock=threading.Lock()
_cache=None
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def market_chart():
    global _cache
    with _lock:
        now=time.time()
        if _cache and now-_cache['fetched_at']<30:return _cache
        request=Request('https://api.bybit.com/v5/market/kline?category=spot&symbol=BTCUSDT&interval=5&limit=300',headers={'User-Agent':'CapitalConnect/1'})
        with build_opener(NoRedirect).open(request,timeout=8) as response:data=json.load(response)
        result=data.get('result',{})
        if data.get('retCode')!=0 or result.get('symbol')!='BTCUSDT' or result.get('category')!='spot':raise ValueError('Unexpected market data')
        points=[]
        for row in result['list']:
            ts=int(row[0])/1000;price=Decimal(row[4])
            if not price.is_finite() or price<=0 or not now-90000<ts<=now:raise ValueError('Invalid candle')
            points.append({'ts':ts,'price':str(price)})
        points.sort(key=lambda p:p['ts'])
        if not points or now-points[-1]['ts']>600:raise ValueError('Market data is stale')
        _cache={'symbol':'BTCUSDT','fetched_at':now,'points':points}
        return _cache
