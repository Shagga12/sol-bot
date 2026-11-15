"""Exercise integrated protected worker recovery. Testnet-only cleanup."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
from .live import Config,Worker,Halt,number,D
from .protected import ProtectedJournal,ProtectedWorker,list_open_orders
from .testnet_exchange import TestnetOnly,settle
from .testnet_lifecycle import close_remaining


def run_case(config,api,directory,phase):
    if config.environment!='testnet' or api.base!='https://api-testnet.bybit.com':
        raise Halt('Protected-worker tests refuse mainnet')
    journal=ProtectedJournal(str(Path(directory)/'protected-worker.sqlite3'),config,api.identity())
    try:
        journal.db.execute('CREATE TABLE IF NOT EXISTS protected_worker_test(id INTEGER PRIMARY KEY CHECK(id=1),stage TEXT)')
        journal.db.execute("INSERT OR IGNORE INTO protected_worker_test VALUES(1,'NEW')")
        stage=journal.db.execute('SELECT stage FROM protected_worker_test').fetchone()[0]
        if stage=='DONE':print('Testnet protected worker: previously completed',flush=True);return 0
        worker=ProtectedWorker(config,api,journal)
        if phase=='create':
            if stage!='NEW':print('Testnet protected-worker entry intent preserved',flush=True);return 0
            rules,bid,ask,fee=worker.snapshot()
            payload=worker.payload('Buy',min(D('15'),number(config.order_usdt),api.available('Buy')),rules,bid,ask,fee,int(time.time()))
            journal.db.execute("UPDATE protected_worker_test SET stage='ENTRY_INTENT' WHERE id=1")
            worker.submit(payload,int(time.time()))
            # Read-only retries accommodate propagation; never retry the entry POST.
            for _ in range(15):
                try:worker.reconcile(int(time.time()))
                except Halt as error:
                    if str(error) not in ('Pending order not found; inspect Bybit before any further submission',
                        'Execution totals not yet reconciled','Attached protection could not be uniquely verified; inspect exchange holdings'):
                        raise
                found=journal.db.execute("SELECT child_id FROM live_protection WHERE state='ACTIVE'").fetchone()
                if found:
                    journal.db.execute("UPDATE protected_worker_test SET stage='PROTECTED' WHERE id=1")
                    print(json.dumps({'integrated_testnet_protection':'ACTIVE','child_id':found[0],
                        'action':'Creator process exits; next process must recover same protection',
                        'mainnet_orders_submitted':0}),flush=True)
                    return 0
                time.sleep(1)
            raise Halt('Integrated protection adoption incomplete; journal preserved')
        if stage!='PROTECTED':raise Halt('Protected test entry not ready for recovery')
        # This invocation is a separate OS process from creation.
        worker.reconcile(int(time.time()))
        record=journal.db.execute("SELECT * FROM live_protection WHERE state='ACTIVE'").fetchone()
        if not record:raise Halt('Expected recorded protective order after restart')
        active=[r for r in list_open_orders(api,config.symbol) if r['orderId']==record['child_id']]
        if len(active)!=1:raise Halt('Recorded protective exit no longer open')
        print(json.dumps({'protected_worker_restart_recovery':'PASSED',
            'exchange_protection_survived_process_exit':True,'child_id':record['child_id'],
            'entry_orders_recorded':journal.db.execute("SELECT COUNT(*) FROM live_orders WHERE side='Buy'").fetchone()[0],
            'mainnet_orders_submitted':0}),flush=True)
        # Cancel and close only this isolated test's recorded assets/orders.
        api.request('/v5/order/cancel',{'category':'spot','symbol':config.symbol,
                    'orderId':record['child_id'],'orderFilter':'tpslOrder'},write=True)
        generic=Worker(config,api,journal)
        settle(generic)
        qty,cost=close_remaining(config,api,journal)
        journal.db.execute("UPDATE live_protection SET state='COMPLETED'")
        journal.db.execute("UPDATE protected_worker_test SET stage='DONE' WHERE id=1")
        print(json.dumps({'integrated_testnet_protected_worker':'PASSED','test_cleanup_complete':True,
                          'remaining_test_btc':str(qty),'pending_orders':len(journal.pending()),
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
        c=Config(**json.loads(Path(args.config).read_text()))
        api=TestnetOnly(c,os.getenv('BYBIT_TESTNET_API_KEY'),os.getenv('BYBIT_TESTNET_API_SECRET'))
        with open(str(Path(args.directory)/'protected-worker.lock'),'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return run_case(c,api,args.directory,args.phase)
    except (Halt,ValueError,TypeError,OSError) as error:
        print(json.dumps({'testnet_protected_worker':'HALTED','reason':str(error) if isinstance(error,Halt) else type(error).__name__,
                          'action':'Preserve Testnet journal; no automatic POST retry','mainnet_orders_submitted':0}),flush=True)
        return 1
if __name__=='__main__':raise SystemExit(main())
