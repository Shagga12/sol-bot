"""Read-only chart projection of the original execution journal; no exchange calls."""
import json
import sqlite3
from pathlib import Path
from decimal import Decimal
from dataclasses import asdict

def verified_exit_reason(result, side):
    """Only label exits when Bybit's reconciled order explicitly identifies them."""
    if side != 'Sell':
        return None
    kind = result.get('stop_order_type')
    if kind in ('StopLoss', 'PartialStopLoss', 'tpslOrder'):
        return 'Stop-loss' if kind != 'tpslOrder' else 'TP/SL (trigger unspecified)'
    if kind in ('TakeProfit', 'PartialTakeProfit'):
        return 'Take-profit'
    return 'Unverified exit'


def chart_snapshot(directory, config):
    path=Path(directory)/'execution-journal.sqlite3'
    if not path.exists():return None
    db=None
    try:
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
        db.row_factory=sqlite3.Row
        db.execute('BEGIN')
        if json.loads(db.execute('SELECT binding FROM live_meta WHERE id=1').fetchone()[0])['config']!=asdict(config):return None
        rows=db.execute('SELECT side,result,pnl,settled,created FROM live_orders WHERE terminal=1 ORDER BY settled,created,link').fetchall()
        fills=[];pnl=Decimal(0)
        for row in rows:
            result=json.loads(row['result']);qty=Decimal(result['executed_qty']);value=Decimal(result['executed_value'])
            pnl+=Decimal(row['pnl'])
            if qty>0:
                fills.append({'ts':row['settled'],'side':row['side'],'price':str(value/qty),'qty':str(qty),'pnl':str(pnl),
                              'exit_reason':verified_exit_reason(result,row['side'])})
        position=db.execute('SELECT qty,cost FROM live_position WHERE id=1').fetchone()
        qty=Decimal(position['qty']);levels=[]
        for row in db.execute("SELECT data FROM live_protection WHERE state='ACTIVE'"):
            data=json.loads(row['data'])
            levels.extend([{'label':'Take profit','price':data['takeProfit']},{'label':'Stop loss','price':data['stopLoss']}])
        if qty>0:levels.insert(0,{'label':'Entry cost / BTC','price':str(Decimal(position['cost'])/qty)})
        return {'fills':fills[-100:],'levels':levels[:3],'total_fills':len(fills)}
    except (sqlite3.Error,ValueError,KeyError,TypeError,IndexError,ArithmeticError):return None
    finally:
        if db is not None:db.close()
