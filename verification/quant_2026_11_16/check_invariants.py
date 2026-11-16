"""Additional deterministic audit checks; no credentials or network calls."""
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from capital_connect_v1.quant_backtest import backtest
from capital_connect_v1.quant_research import analyze_prices

def reference(prices, fee=.001):
    equity=peak=1000.; drawdown=fees=0.; position=trades=0
    for i in range(30,len(prices)-1):
        action=analyze_prices(prices[i-30:i+1]).action
        target=1 if action=='BUY_CANDIDATE' else 0 if action=='SELL_CANDIDATE' else position
        if target!=position:
            cost=equity*fee; equity-=cost; fees+=cost; trades+=1; position=target
        if position: equity*=prices[i+1]/prices[i]
        peak=max(peak,equity); drawdown=max(drawdown,(peak-equity)/peak)
    return equity,trades,fees,drawdown*100

random.seed(8642)
for case in range(100):
    prices=[100.]
    for i in range(250): prices.append(prices[-1]*(1+random.uniform(-.025,.025)))
    actual=backtest(prices); expected=reference(prices)
    assert abs(actual.ending_usdt-expected[0])<1e-8
    assert actual.trades==expected[1]
    assert abs(actual.fees_usdt-expected[2])<1e-8
    assert abs(actual.max_drawdown_pct-expected[3])<1e-8
prices=[100+i*.2 for i in range(100)]
prefix=[analyze_prices(prices[:i+1]) for i in range(31,100)]
for future in [1.,1000000.]:
    extended=prices+[future]
    assert prefix==[analyze_prices(extended[:i+1]) for i in range(31,100)]
for invalid in [float('nan'),float('inf'),0.,-1.]:
    assert analyze_prices([100.]*30+[invalid]).action=='WAIT'
    try: backtest([100.]*39+[invalid])
    except ValueError: pass
    else: raise AssertionError('Invalid price was accepted')
print('PASS: 100 streaming parity paths, future-shock prefix invariance, invalid prices')
