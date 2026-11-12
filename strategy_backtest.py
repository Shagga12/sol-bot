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


def replay(bars, filters, *, dust_policy='halt'):
    if dust_policy not in {'halt','quarantine'}: raise ValueError('Select an explicit supported dust policy')
    if len(bars)<52: raise DataUnavailable('At least 52 completed bars required')
    for i,b in enumerate(bars):
        if (type(b['start_ms']) is not int or b['start_ms']%INTERVAL_MS
                or (i and b['start_ms']-bars[i-1]['start_ms']!=INTERVAL_MS)):
            raise DataUnavailable('Backtest data is gapped, unaligned or out of order')
        o,h,l,c=(n(b[field]) for field in ('open','high','low','close'))
        if h<max(o,c) or l>min(o,c) or h<l: raise DataUnavailable('Inconsistent OHLC prices')
    cash=n(POLICY['initial_simulated_usdt']); initial=cash
    step=n(filters['base_step']); minimum=n(filters['minimum_notional'])
    fee=n(POLICY['fee_rate']); execution=n(POLICY['one_way_execution_cost_fraction'])
    qty=cost=dust_qty=dust_cost=Decimal(0)
    pending=None; halted=None; exit_blocked=False
    trades=[]; entries={}; losses={}; events=[]
    entry_skips=exit_skips=blocked_exit_bars=0
    peak=initial; drawdown=Decimal(0)
    closed=[n(b['close']) for b in bars]
    for i,bar in enumerate(bars):
        day=day_key(bar['start_ms'])
        entries.setdefault(day,0); losses.setdefault(day,Decimal(0))
        if pending=='BUY' and qty==0 and halted is None:
            if entries[day]<2 and losses[day]<initial*Decimal('.02'):
                price=n(bar['open'])*(1+execution)
                gross=(cash/price/step).to_integral_value(rounding=ROUND_DOWN)*step
                value=gross*price
                if value>=minimum:
                    qty=gross*(1-fee)
                    cost=value; cash-=value; entries[day]+=1
                    trades.append({'side':'BUY','time_ms':bar['start_ms'],'price':str(price),
                                   'gross_qty':str(gross),'net_qty':str(qty),'cost_usdt':str(cost)})
                else: entry_skips+=1
        elif pending=='SELL' and qty>0 and halted is None:
            price=n(bar['open'])*(1-execution)
            sell_qty=(qty/step).to_integral_value(rounding=ROUND_DOWN)*step
            value=sell_qty*price
            if value>=minimum and sell_qty>0:
                proceeds=value*(1-fee); removed=cost*sell_qty/qty
                pnl=proceeds-removed; cash+=proceeds
                qty-=sell_qty; cost-=removed; losses[day]+=max(-pnl,Decimal(0))
                exit_blocked=False
                trades.append({'side':'SELL','time_ms':bar['start_ms'],'price':str(price),
                               'qty':str(sell_qty),'net_proceeds_usdt':str(proceeds),'realized_pnl_usdt':str(pnl)})
                if 0<qty<step:
                    events.append({'time_ms':bar['start_ms'],'type':'BELOW_QUANTITY_STEP_AFTER_EXIT',
                                   'qty':str(qty),'cost_usdt':str(cost),'policy':dust_policy})
                    if dust_policy=='halt':
                        halted='UNSELLABLE_DUST_BLOCKS_NEW_ENTRIES'
                    else:
                        # Simulation-only policy alternative. Preserve every unit
                        # and its cost; never convert dust into cash or a profit.
                        dust_qty+=qty; dust_cost+=cost; qty=cost=Decimal(0)
            else:
                if not exit_blocked: exit_skips+=1
                exit_blocked=True
        pending=None
        equity=cash+(qty+dust_qty)*closed[i]*(1-execution)*(1-fee)
        peak=max(peak,equity); drawdown=max(drawdown,(peak-equity)/peak)
        # All signals use a completed bar. Fills occur on the next bar's open.
        up=down=False
        if i>=50:
            pf=sum(closed[i-20:i])/20; ps=sum(closed[i-50:i])/50
            cf=sum(closed[i-19:i+1])/20; cs=sum(closed[i-49:i+1])/50
            up=pf<=ps and cf>cs; down=pf>=ps and cf<cs
        if qty>0 and halted is None:
            estimated=qty*closed[i]*(1-execution)*(1-fee)
            change=(estimated-cost)/cost
            if change>=Decimal('.02') or change<=Decimal('-.01') or down:
                sell_qty=(qty/step).to_integral_value(rounding=ROUND_DOWN)*step
                if sell_qty>0 and sell_qty*closed[i]*(1-execution)>=minimum:
                    pending='SELL'
                else:
                    if not exit_blocked: exit_skips+=1
                    exit_blocked=True; blocked_exit_bars+=1
        elif qty==0 and halted is None and up and entries[day]<2 and losses[day]<initial*Decimal('.02'):
            pending='BUY'
    realized=sum((Decimal(t.get('realized_pnl_usdt','0')) for t in trades),Decimal(0))
    return {'mode':'HISTORICAL_SIMULATION_ONLY','live_trading_ready':False,'model_version':2,
            'dust_policy':dust_policy,'halt_reason':halted,
            'initial_usdt':str(initial),'ending_cash_usdt':str(cash),
            'remaining_base_qty':str(qty+dust_qty),'active_position_base_qty':str(qty),
            'quarantined_dust_qty':str(dust_qty),'quarantined_dust_cost_usdt':str(dust_cost),
            'remaining_cost_usdt':str(cost+dust_cost),
            'ending_equity_after_estimated_exit_costs':str(equity),
            'equity_is_not_spendable_cash':True,
            'total_return_fraction':str((equity-initial)/initial),'realized_pnl_usdt':str(realized),
            'maximum_mark_to_market_drawdown_fraction':str(drawdown),
            'entries':sum(t['side']=='BUY' for t in trades),'exit_fills':sum(t['side']=='SELL' for t in trades),
            'minimum_notional_skips':entry_skips+exit_skips,'entry_minimum_skips':entry_skips,
            'exit_minimum_block_events':exit_skips,'bars_with_blocked_exit_signal':blocked_exit_bars,
            'dust_event_count':len(events),'dust_events':events,
            'pending_final_signal_not_executed':pending,'trades':trades,
            'limitations':['Not a live-execution or profitability guarantee',
              'Current filters are a proxy, not historical filter versions',
              'Fees and adverse execution costs are assumptions, not account rates or orderbook replay',
              'No intrabar protective-stop fills, historical spreads, liquidity model or network failures',
              'Dust and open positions remain marked, not liquidated or credited to cash',
              'Quarantine is an explicit alternative simulation policy, not an approved live rule',
              'No commissions debited, withdrawals or real orders']}


def data_hash(bars):
    return hashlib.sha256(json.dumps(bars,sort_keys=True).encode()).hexdigest()


def make_bundle(bars, filters):
    return {'schema_version':1,'source':'Bybit public BTCUSDT spot 15-minute klines',
            'symbol':'BTCUSDT','interval_minutes':15,'filter_proxy':filters,
            'dataset_sha256':data_hash(bars),'bars':bars}


def load_bundle(path):
    bundle=json.loads(Path(path).read_text(encoding='utf-8'))
    if (bundle.get('schema_version')!=1 or bundle.get('symbol')!='BTCUSDT'
            or bundle.get('interval_minutes')!=15 or not isinstance(bundle.get('bars'),list)
            or bundle.get('dataset_sha256')!=data_hash(bundle['bars'])):
        raise DataUnavailable('Saved market-data identity or checksum does not match')
    return bundle['bars'],bundle['filter_proxy']


def summary(value):
    if isinstance(value,dict): return {k:summary(v) for k,v in value.items() if k not in {'trades','dust_events'}}
    if isinstance(value,list): return [summary(v) for v in value]
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=int,default=90)
    parser.add_argument('--output',default='backtest-results.json')
    parser.add_argument('--dust-policy',choices=['halt','quarantine','compare'],default='halt')
    parser.add_argument('--save-data',help='Save public candles and filter proxy for reproducible offline tests')
    parser.add_argument('--data-file',help='Replay a previously saved public-data bundle without network access')
    args=parser.parse_args()
    report={'status':'FAILED','live_trading_ready':False}
    try:
        if args.data_file: bars,filters=load_bundle(args.data_file)
        else: bars,filters=download(args.days),current_filters()
        if args.save_data:
            Path(args.save_data).write_text(json.dumps(make_bundle(bars,filters)),encoding='utf-8')
        if args.dust_policy=='compare':
            report={'mode':'HISTORICAL_SIMULATION_COMPARISON_ONLY','live_trading_ready':False,
                    'models':{p:replay(bars,filters,dust_policy=p) for p in ['halt','quarantine']}}
        else: report=replay(bars,filters,dust_policy=args.dust_policy)
        report.update(status='COMPLETED',source='Bybit public BTCUSDT spot 15-minute klines',
                      candle_count=len(bars),start_ms=bars[0]['start_ms'],
                      end_ms=bars[-1]['start_ms']+INTERVAL_MS,policy=POLICY,filter_proxy=filters,
                      dataset_sha256=data_hash(bars))
    except Exception as error:
        report={'status':'FAILED','live_trading_ready':False,
                'error':str(error) if isinstance(error,(DataUnavailable,ValueError)) else 'Market data or simulation failed'}
    Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(summary(report),indent=2))
    return 0 if report['status']=='COMPLETED' else 1


if __name__=='__main__': raise SystemExit(main())
