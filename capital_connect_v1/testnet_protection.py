"""Test exchange-attached exits across process shutdown; Testnet only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
from .live import Config, Journal, Worker, Halt, number, D
from .protection import attach_protection
from .testnet_exchange import TestnetOnly, settle
from .testnet_lifecycle import close_remaining


def open_orders(api,symbol):
    rows=[];cursor='';seen=set()
    while True:
        page=api.request('/v5/order/realtime',{'category':'spot','symbol':symbol,'limit':50,
                         **({'cursor':cursor} if cursor else {})})
        rows.extend(page.get('list',[]))
        cursor=page.get('nextPageCursor')
        if not cursor:return rows
        if cursor in seen or len(rows)>1000:raise Halt('Protection pagination incomplete')
        seen.add(cursor)


def probe(config,api,directory,phase):
    if config.environment!='testnet' or api.base!='https://api-testnet.bybit.com':
        raise Halt('Protection tests refuse mainnet')
    journal=Journal(str(Path(directory)/'protection-test.sqlite3'),config,api.identity())
    try:
        journal.db.execute('CREATE TABLE IF NOT EXISTS protection_probe(id INTEGER PRIMARY KEY CHECK(id=1), stage TEXT, data TEXT)')
        journal.db.execute("INSERT OR IGNORE INTO protection_probe VALUES(1,'NEW','{}')")
        row=journal.db.execute('SELECT stage,data FROM protection_probe').fetchone()
        stage=row['stage'];data=json.loads(row['data'])
        if stage=='DONE':print('Testnet protection: previously completed; no new orders',flush=True);return 0
        worker=Worker(config,api,journal)
        if phase=='create':
            if stage!='NEW':print('Testnet protection: existing intent preserved',flush=True);return 0
            if journal.position()!=(D(0),D(0)) or journal.pending():raise Halt('Unexpected test holdings')
            before=[r['orderId'] for r in open_orders(api,config.symbol)]
            rules,bid,ask,fee=worker.snapshot()
            amount=min(D('15'),number(config.order_usdt),api.available('Buy'))
            payload=attach_protection(worker.payload('Buy',amount,rules,bid,ask,fee,int(time.time())),config,rules,fee)
            data={'before':before,'takeProfit':payload['takeProfit'],'stopLoss':payload['stopLoss']}
            journal.db.execute("UPDATE protection_probe SET stage='BUY_INTENT',data=? WHERE id=1",(json.dumps(data),))
            worker.submit(payload,int(time.time()))
            journal.db.execute("UPDATE protection_probe SET stage='BUY_ACCEPTED' WHERE id=1")
            print('Testnet protected buy accepted; creator process exits before protection verification',flush=True)
            return 0
        if stage not in ('BUY_INTENT','BUY_ACCEPTED','CHILD_FOUND','CANCEL_REQUESTED'):
            raise Halt('No protected test buy for verification')
        settle(worker)
        qty,cost=journal.position()
        if qty<=0:raise Halt('Protected test entry has no fills')
        if not data.get('child_id'):
            candidates=[]
            for _ in range(10):
                fresh=[r for r in open_orders(api,config.symbol) if r['orderId'] not in data['before']]
                # This isolated Testnet account has no concurrent strategy. Require
                # a unique matching sell bracket and preserve its exact exchange ID.
                candidates=[r for r in fresh if r.get('side')=='Sell' and
                    r.get('takeProfit') and r.get('stopLoss') and
                    number(r['takeProfit'])==number(data['takeProfit']) and
                    number(r['stopLoss'])==number(data['stopLoss'])]
                if candidates:break
                time.sleep(1)
            if len(candidates)!=1:
                safe=[{k:r.get(k) for k in ('orderId','orderLinkId','side','qty','orderType','stopOrderType','orderStatus','takeProfit','stopLoss','triggerPrice')} for r in fresh]
                print(json.dumps({'testnet_protection_observation':safe}),flush=True)
                raise Halt('Could not uniquely verify an exchange-held attached bracket')
            child=candidates[0]
            child_qty=number(child['qty'],True)
            if child_qty>qty:raise Halt('Attached exit exceeds net bot-owned test quantity')
            data['child_id']=child['orderId'];data['child_qty']=str(child_qty)
            journal.db.execute("UPDATE protection_probe SET stage='CHILD_FOUND',data=? WHERE id=1",(json.dumps(data),))
            print(json.dumps({'exchange_held_testnet_bracket':'VERIFIED','creator_process_exited':True,
                'child_id':data['child_id'],'child_qty':str(child_qty),'takeProfit':data['takeProfit'],
                'stopLoss':data['stopLoss'],'mainnet_orders_submitted':0}),flush=True)
        # Cleanup is explicit and Testnet-only. No cancel-all or unrelated order IDs.
        journal.db.execute("UPDATE protection_probe SET stage='CANCEL_REQUESTED' WHERE id=1")
        api.request('/v5/order/cancel',{'category':'spot','symbol':config.symbol,
                    'orderId':data['child_id'],'orderFilter':'tpslOrder'},write=True)
        for _ in range(15):
            if not any(r['orderId']==data['child_id'] for r in open_orders(api,config.symbol)):break
            time.sleep(1)
        else:raise Halt('Test bracket cancellation not confirmed; no manual sell submitted')
        qty,cost=close_remaining(config,api,journal)
        journal.db.execute("UPDATE protection_probe SET stage='DONE' WHERE id=1")
        print(json.dumps({'testnet_exchange_protection':'PASSED','bracket_survived_creator_process_exit':True,
                          'test_bracket_cancelled':True,'remaining_test_btc':str(qty),
                          'mainnet_orders_submitted':0,'profitability_verified':False}),flush=True)
        return 0
    finally:journal.db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True);p.add_argument('--directory',required=True)
    p.add_argument('--phase',choices=('create','verify'),required=True);p.add_argument('--testnet-orders',action='store_true')
    args=p.parse_args()
    try:
        if not args.testnet_orders:raise Halt('Explicit Testnet authorization required')
        config=Config(**json.loads(Path(args.config).read_text()))
        api=TestnetOnly(config,os.getenv('BYBIT_TESTNET_API_KEY'),os.getenv('BYBIT_TESTNET_API_SECRET'))
        with open(str(Path(args.directory)/'protection-test.lock'),'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return probe(config,api,args.directory,args.phase)
    except (Halt,ValueError,TypeError,OSError) as error:
        print(json.dumps({'testnet_protection':'HALTED','reason':str(error) if isinstance(error,Halt) else type(error).__name__,
                          'action':'Preserve test journal and inspect Testnet orders; no automatic POST retry',
                          'mainnet_orders_submitted':0}),flush=True)
        return 1
if __name__=='__main__':raise SystemExit(main())
