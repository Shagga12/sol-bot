"""Standalone public-data backtest. No API keys, balances, or order endpoints.

Run: python strategy_backtest.py --days 90 --output backtest-results.json
A historical model, not live execution validation or a profitability guarantee.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_DOWN
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

INTERVAL_MS=900000
POLICY={'symbol':'BTCUSDT','interval_minutes':15,'fast_sma':20,'slow_sma':50,
        'take_profit_net_fraction':'0.02','stop_loss_net_fraction':'0.01',
        'daily_loss_fraction':'0.02','max_daily_entries':2,
        'initial_simulated_usdt':'5.50','fee_rate':'0.001',
        'one_way_execution_cost_fraction':'0.001'}


class DataUnavailable(ValueError): pass


def n(value):
    d=Decimal(str(value))
    if not d.is_finite() or d <= 0: raise DataUnavailable('Invalid positive market amount')
    return d


def public_json(endpoint, params, opener=None):
    if endpoint not in {'/v5/market/kline','/v5/market/instruments-info'}:
        raise ValueError('Only public market-data endpoints are allowed')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    opener=opener or urllib.request.build_opener(NoRedirect)
    req=urllib.request.Request('https://api.bybit.com'+endpoint+'?'+urllib.parse.urlencode(params),
                               headers={'Accept':'application/json'},method='GET')
    try:
        with opener.open(req,timeout=15) as response:
            if response.status != 200: raise DataUnavailable('Market download failed')
            body=json.load(response)
    except Exception:
        raise DataUnavailable('Public Bybit data unavailable from this computer; no retries or alternate domains used') from None
    if not isinstance(body,dict) or type(body.get('retCode')) is not int or body['retCode'] != 0:
        raise DataUnavailable('Exchange did not return successful public data')
    result=body.get('result')
    if not isinstance(result,dict): raise DataUnavailable('Missing market-data result')
    return result


def download(days, now_ms=None, fetch=public_json):
    if type(days) is not int or not 2 <= days <= 180: raise ValueError('Use 2 through 180 days')
    now_ms=now_ms if now_ms is not None else int(time.time()*1000)
    end_boundary=(now_ms//INTERVAL_MS)*INTERVAL_MS
    start=end_boundary-days*86400000
    end=end_boundary-1
    found={}
    for _ in range(30):
        result=fetch('/v5/market/kline',{'category':'spot','symbol':'BTCUSDT','interval':'15',
                      'start':start,'end':end,'limit':1000})
        if result.get('symbol') != 'BTCUSDT' or result.get('category') != 'spot':
            raise DataUnavailable('Unexpected market identity')
        rows=result.get('list')
        if not isinstance(rows,list) or not rows: raise DataUnavailable('Historical coverage is incomplete')
        stamps=[]
        for row in rows:
            if not isinstance(row,list) or len(row)<5: raise DataUnavailable('Invalid candle record')
            stamp=int(row[0])
            if stamp % INTERVAL_MS or stamp<start or stamp>end or stamp+INTERVAL_MS>end_boundary:
                raise DataUnavailable('Unexpected or unclosed candle')
            values=[str(n(v)) for v in row[1:5]]
            o,h,l,c=map(Decimal,values)
            if h<max(o,c) or l>min(o,c) or h<l: raise DataUnavailable('Inconsistent OHLC prices')
            record={'start_ms':stamp,'open':values[0],'high':values[1],'low':values[2],'close':values[3]}
            if stamp in found and found[stamp]!=record: raise DataUnavailable('Conflicting duplicate candle')
            found[stamp]=record
            stamps.append(stamp)
        oldest=min(stamps)
        if oldest<=start: break
        if oldest>=end: raise DataUnavailable('Candle pagination did not advance')
        end=oldest-1
    bars=[found[k] for k in sorted(found)]
    expected=days*96
    if len(bars)!=expected or bars[0]['start_ms']!=start or bars[-1]['start_ms']!=end_boundary-INTERVAL_MS:
        raise DataUnavailable('Historical window has gaps or missing coverage')
    return bars


def current_filters(fetch=public_json):
    result=fetch('/v5/market/instruments-info',{'category':'spot','symbol':'BTCUSDT'})
    records=result.get('list',[])
    if result.get('category')!='spot' or len(records)!=1 or records[0].get('symbol')!='BTCUSDT' or records[0].get('status')!='Trading':
        raise DataUnavailable('Current BTC spot filters unavailable')
    lot=records[0]['lotSizeFilter']
    return {'base_step':str(n(lot['basePrecision'])),'minimum_notional':str(n(lot['minOrderAmt']))}


def day_key(stamp):
    # Tortola has fixed UTC-4; no external timezone database required on Windows.
    from datetime import timedelta
    return datetime.fromtimestamp(stamp/1000,timezone(timedelta(hours=-4))).date().isoformat()


def replay(bars, filters):
    if len(bars)<52: raise DataUnavailable('At least 52 completed bars required')
    for i,b in enumerate(bars):
        if i and b['start_ms']-bars[i-1]['start_ms']!=INTERVAL_MS:
            raise DataUnavailable('Backtest data is gapped or out of order')
        for field in ('open','high','low','close'): n(b[field])
    cash=n(POLICY['initial_simulated_usdt'])
    initial=cash
    step=n(filters['base_step']); minimum=n(filters['minimum_notional'])
    fee=n(POLICY['fee_rate']); execution=n(POLICY['one_way_execution_cost_fraction'])
    qty=cost=Decimal(0)
    pending=None
    trades=[]; entries={}; losses={}; skipped=0; peak=initial; drawdown=Decimal(0)
    closed=[n(b['close']) for b in bars]
    for i,bar in enumerate(bars):
        day=day_key(bar['start_ms'])
        entries.setdefault(day,0); losses.setdefault(day,Decimal(0))
        # Signal from the PREVIOUS completed bar fills at this bar's open,
        # with adverse execution cost. Never use this bar's close for its entry.
        if pending=='BUY' and qty==0:
            if entries[day]<2 and losses[day]<initial*Decimal('.02'):
                price=n(bar['open'])*(1+execution)
                gross=(cash/price/step).to_integral_value(rounding=ROUND_DOWN)*step
                value=gross*price
                if value>=minimum:
                    qty=gross*(1-fee)  # Buy fee charged in acquired base asset.
                    cost=value
                    cash-=value
                    entries[day]+=1
                    trades.append({'side':'BUY','time_ms':bar['start_ms'],'price':str(price),
                                   'gross_qty':str(gross),'net_qty':str(qty),'cost_usdt':str(cost)})
                else: skipped+=1
        elif pending=='SELL' and qty>0:
            price=n(bar['open'])*(1-execution)
            sell_qty=(qty/step).to_integral_value(rounding=ROUND_DOWN)*step
            value=sell_qty*price
            if value>=minimum and sell_qty>0:
                proceeds=value*(1-fee)
                removed=cost*sell_qty/qty
                pnl=proceeds-removed
                cash+=proceeds
                qty-=sell_qty; cost-=removed
                losses[day]+=max(-pnl,Decimal(0))
                trades.append({'side':'SELL','time_ms':bar['start_ms'],'price':str(price),
                               'qty':str(sell_qty),'net_proceeds_usdt':str(proceeds),'realized_pnl_usdt':str(pnl)})
            else: skipped+=1
        pending=None
        equity=cash+qty*closed[i]*(1-execution)*(1-fee)
        peak=max(peak,equity)
        drawdown=max(drawdown,(peak-equity)/peak)
        # Evaluation is close-only; intrabar touches are intentionally NOT
        # modelled as guaranteed protective fills. An always-on stop must be
        # tested separately. This is a conservative scheduling model, not L2 replay.
        up=down=False
        if i>=50:
            pf=sum(closed[i-20:i])/20; ps=sum(closed[i-50:i])/50
            cf=sum(closed[i-19:i+1])/20; cs=sum(closed[i-49:i+1])/50
            up=pf<=ps and cf>cs; down=pf>=ps and cf<cs
        if qty>0:
            estimated=qty*closed[i]*(1-execution)*(1-fee)
            change=(estimated-cost)/cost
            if change>=Decimal('.02') or change<=Decimal('-.01') or down:
                pending='SELL'
        elif up and entries[day]<2 and losses[day]<initial*Decimal('.02'):
            pending='BUY'
    realized=sum((Decimal(t.get('realized_pnl_usdt','0')) for t in trades),Decimal(0))
    return {'mode':'HISTORICAL_SIMULATION_ONLY','live_trading_ready':False,
            'initial_usdt':str(initial),'ending_cash_usdt':str(cash),
            'remaining_base_qty':str(qty),'remaining_cost_usdt':str(cost),
            'ending_equity_after_estimated_exit_costs':str(equity),
            'total_return_fraction':str((equity-initial)/initial),
            'realized_pnl_usdt':str(realized),'maximum_mark_to_market_drawdown_fraction':str(drawdown),
            'entries':sum(t['side']=='BUY' for t in trades),
            'exit_fills':sum(t['side']=='SELL' for t in trades),'minimum_notional_skips':skipped,
            'pending_final_signal_not_executed':pending,'trades':trades,
            'limitations':['Not a live-execution or profitability guarantee',
              'Uses current filters as a proxy, not historical filter versions',
              'Fee and adverse execution cost are assumptions, not account rates or orderbook replay',
              'No intrabar stop fills, liquidity modelling or network failures',
              'Dust and open positions remain marked, not forced closed',
              'Signal evaluator uses spread guards; candle replay cannot verify historical spreads',
              'No commissions debited and no withdrawals or real orders']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=int,default=90)
    parser.add_argument('--output',default='backtest-results.json')
    args=parser.parse_args()
    report={'status':'FAILED','live_trading_ready':False}
    try:
        bars=download(args.days)
        filters=current_filters()
        report=replay(bars,filters)
        report.update(status='COMPLETED',source='Bybit public BTCUSDT spot 15-minute klines',
                      candle_count=len(bars),start_ms=bars[0]['start_ms'],
                      end_ms=bars[-1]['start_ms']+INTERVAL_MS,policy=POLICY,filter_proxy=filters,
                      dataset_sha256=hashlib.sha256(json.dumps(bars,sort_keys=True).encode()).hexdigest())
    except Exception as error:
        report['error']=str(error) if isinstance(error,(DataUnavailable,ValueError)) else 'Market data or simulation failed'
    Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='trades'},indent=2))
    return 0 if report['status']=='COMPLETED' else 1


if __name__=='__main__': raise SystemExit(main())
