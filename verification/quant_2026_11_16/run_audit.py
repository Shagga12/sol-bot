import sys,json,datetime,math,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from capital_connect_v1.quant_research import analyze_prices
from capital_connect_v1.quant_backtest import backtest
raw=json.load(open('/tmp/quant-official-btcusd-2025.json'));rows=raw['rows']
assert not raw['missing']
for r in rows:
 o,h,l,c=(float(r[k]) for k in ('open','high','low','close'))
 assert all(math.isfinite(v) and v>0 for v in (o,h,l,c)) and l<=min(o,c)<=max(o,c)<=h
# Cost-adjusted streaming implementation, already checked against original model.
def run(rs, cost=.001, next_open=False):
 p=[float(r['close']) for r in rs];eq=peak=1000.;dd=fees=0.;pos=trades=exits=0
 for i in range(30,len(p)-1):
  action=analyze_prices(p[i-30:i+1]).action
  target=1 if action=='BUY_CANDIDATE' else 0 if action=='SELL_CANDIDATE' else pos
  if next_open:
   opening=float(rs[i+1]['open'])
   if pos:eq*=opening/p[i]
  if target!=pos:
   f=eq*cost;eq-=f;fees+=f;trades+=1;exits+=int(target==0);pos=target
  if pos:eq*=p[i+1]/(float(rs[i+1]['open']) if next_open else p[i])
  peak=max(peak,eq);dd=max(dd,(peak-eq)/peak)
 marked=eq
 # Terminal liquidation for comparable cash result, absent in existing module.
 if pos:
  f=eq*cost;eq-=f;fees+=f;exits+=1
 peak=max(peak,eq);dd=max(dd,(peak-eq)/peak)
 hold=1000*(1-cost)*p[-1]/p[30]*(1-cost)
 return {'net_return_pct':(eq/1000-1)*100,'max_drawdown_pct':dd*100,'position_changes':trades,'completed_round_trips_including_terminal_liquidation':exits,'fees_usdt_per_1000':fees,'buy_hold_net_pct':(hold/1000-1)*100,'marked_before_terminal_fee_usdt':marked}
results={'commit':'1841934c9bddc1d1ad0fc73fc931abc77c50697a','source':'https://www.bitstamp.net/api/v2/ohlc/btcusd/','period':'2025-01-01 through 2025-12-31 UTC','candles':len(rows),'missing_candles':len(raw['missing']),'configuration':{'fast':10,'slow':30,'max_volatility':.04,'trend_spread_threshold':.002},'full_year':{},'quarterly_next_open_20bps':{}}
for cost in [.001,.002,.003]:
 results['full_year'][str(cost)]={'same_close':run(rows,cost),'next_open':run(rows,cost,True)}
for q in range(1,5):
 rs=[r for r in rows if (datetime.datetime.fromtimestamp(int(r['timestamp']),datetime.timezone.utc).month-1)//3+1==q]
 results['quarterly_next_open_20bps'][str(q)]={'candles':len(rs),**run(rs,.002,True)}
# Match the actual deployed implementation on real candles, with no altered code.
real=[float(r['close']) for r in rows[:3000]]
a=backtest(real);b=run(rows[:3000]);assert abs(a.ending_usdt-b['marked_before_terminal_fee_usdt'])<1e-7
results['actual_module_vs_independent_model_3000_real_candles']='PASS'
open('/tmp/quant-audit-results.json','w').write(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
