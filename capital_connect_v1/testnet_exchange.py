"""Bounded, restartable virtual-funds exchange tests. Testnet host only.
No mainnet configuration or keys are accepted. Never retries an uncertain POST.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
from .live import Bybit, Config, Halt, Journal, Worker, number, D


class TestnetOnly(Bybit):
    def __init__(self, config, key, secret, **kwargs):
        if config.environment != 'testnet':
            raise Halt('Testnet validation refuses mainnet')
        super().__init__(config, key, secret, allow_orders=True, **kwargs)
        if self.base != 'https://api-testnet.bybit.com':
            raise Halt('Unexpected test host')


def settle(worker, seconds=25):
    deadline = time.monotonic()+seconds
    while True:
        try:
            if worker.reconcile(int(time.time())):
                return
        except Halt as error:
            # Eventual consistency only: repeat GET reconciliation, never POST.
            if str(error) not in ('Pending order not found; inspect Bybit before any further submission',
                                  'Execution totals not yet reconciled'):
                raise
        if time.monotonic() >= deadline:
            raise Halt('Testnet reconciliation incomplete; original journal preserved')
        time.sleep(1)


def phase(config, api, directory, action):
    if config.environment != 'testnet' or api.base != 'https://api-testnet.bybit.com':
        raise Halt('Only Testnet can run validation orders')
    uid = api.identity()
    path = str(Path(directory)/'exchange-tests.sqlite3')
    journal = Journal(path, config, uid)
    try:
        journal.db.execute('CREATE TABLE IF NOT EXISTS validation_suite(id INTEGER PRIMARY KEY CHECK(id=1), stage TEXT)')
        journal.db.execute("INSERT OR IGNORE INTO validation_suite VALUES(1,'NEW')")
        stage = journal.db.execute('SELECT stage FROM validation_suite WHERE id=1').fetchone()[0]
        if stage == 'DONE':
            print('Testnet exchange tests: already completed; no new orders',flush=True)
            return 0
        worker = Worker(config, api, journal)
        if action == 'buy':
            if stage != 'NEW':
                print('Testnet buy: prior intent preserved; not submitting another buy',flush=True)
                return 0
            if journal.position() != (D(0),D(0)) or journal.pending():
                raise Halt('Unexpected prior test position or order')
            rules,bid,ask,fee = worker.snapshot()
            budget = min(number(config.order_usdt), number(config.capital_usdt), api.available('Buy'), D('15'))
            payload = worker.payload('Buy',budget,rules,bid,ask,fee,int(time.time()))
            journal.db.execute("UPDATE validation_suite SET stage='BUY_INTENT' WHERE id=1")
            worker.submit(payload,int(time.time()))
            journal.db.execute("UPDATE validation_suite SET stage='BUY_SUBMITTED' WHERE id=1")
            print('Testnet buy accepted; exiting process before fill reconciliation; journal preserved',flush=True)
            return 0
        if stage not in ('BUY_INTENT','BUY_SUBMITTED','SELL_INTENT','SELL_SUBMITTED'):
            raise Halt('No test buy available for recovery')
        # A NEW process reconstructs holdings only from journalled exchange fills.
        settle(worker)
        qty,cost = journal.position()
        if stage in ('BUY_INTENT','BUY_SUBMITTED'):
            if qty <= 0:
                raise Halt('Testnet buy has no fill; validation incomplete; no blind retry')
            rules,bid,ask,fee = worker.snapshot()
            payload = worker.payload('Sell',min(qty,api.available('Sell')),rules,bid,ask,fee,int(time.time()))
            journal.db.execute("UPDATE validation_suite SET stage='SELL_INTENT' WHERE id=1")
            worker.submit(payload,int(time.time()))
            journal.db.execute("UPDATE validation_suite SET stage='SELL_SUBMITTED' WHERE id=1")
            settle(worker)
        qty,cost = journal.position()
        rules,bid,ask,fee = worker.snapshot()
        if qty*bid >= number(rules['lotSizeFilter']['minOrderAmt'],True):
            raise Halt('Testnet sell left a tradable holding; original journal preserved')
        sells=journal.db.execute("SELECT COUNT(*) FROM live_orders WHERE side='Sell' AND terminal=1 AND CAST(json_extract(result,'$.executed_qty') AS REAL)>0").fetchone()[0]
        if not sells:
            raise Halt('No filled Testnet sell was reconciled')
        journal.db.execute("UPDATE validation_suite SET stage='DONE' WHERE id=1")
        print(json.dumps({'testnet_exchange_roundtrip':'PASSED','restart_reconciliation':'PASSED',
            'pending_orders':len(journal.pending()),'remaining_test_btc':str(qty),
            'retained_dust_cost_usdt':str(cost),'testnet_realized_pnl_usdt':str(journal.pnl()),
            'mainnet_orders_submitted':0,'profitability_verified':False,
            'remaining_validation':['profit/loss trigger paths against exchange','Start/Stop with running exchange worker']}),flush=True)
        return 0
    finally:
        journal.db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--directory',required=True)
    parser.add_argument('--phase',choices=('buy','close'),required=True)
    parser.add_argument('--testnet-orders',action='store_true')
    args=parser.parse_args()
    try:
        if not args.testnet_orders: raise Halt('Explicit Testnet validation authorization required')
        config=Config(**json.loads(Path(args.config).read_text()))
        api=TestnetOnly(config,os.getenv('BYBIT_TESTNET_API_KEY'),os.getenv('BYBIT_TESTNET_API_SECRET'))
        with open(str(Path(args.directory)/'exchange-tests.lock'),'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return phase(config,api,args.directory,args.phase)
    except (Halt,ValueError,TypeError,OSError) as error:
        print(json.dumps({'testnet_exchange_tests':'HALTED','reason':str(error) if isinstance(error,Halt) else type(error).__name__,
                          'mainnet_orders_submitted':0,'action':'Preserve the test journal; no automatic POST retry'}),flush=True)
        return 1

if __name__=='__main__': raise SystemExit(main())
