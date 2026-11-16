"""Virtual-funds lifecycle validation. Synthetic triggers; real Testnet fills.
No mainnet host or mainnet credentials are used. Never retries uncertain POSTs.
"""
import argparse
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import time
from .live import Config, Journal, Worker, Halt, number, D
from .testnet_exchange import TestnetOnly, settle
from .supervised_worker import Supervisor


class TriggeredWorker(Worker):
    def __init__(self, config, api, journal, trigger):
        if config.environment != 'testnet' or api.base != 'https://api-testnet.bybit.com':
            raise Halt('Synthetic lifecycle tests refuse mainnet')
        super().__init__(config,api,journal)
        self.trigger=trigger
        self.triggered=False
    def snapshot(self):
        rules,bid,ask,fee=super().snapshot()
        qty,cost=self.journal.position()
        if qty and cost:
            change=(number(self.c.take_profit_fraction)+D('.001') if self.trigger=='profit'
                    else -number(self.c.stop_loss_fraction)-D('.001'))
            bid=cost/qty*(1+change)/((1-number(self.c.slippage_percent)/100)*(1-fee))
            self.triggered=True
            return rules,bid,bid,fee
        return rules,bid,ask,fee
    def payload(self,side,amount,rules,bid,ask,fee,now):
        # Controlled price drives the decision only. The order uses a fresh real
        # Testnet quote, so synthetic prices never become exchange order prices.
        rules,bid,ask,fee=Worker.snapshot(self)
        return super().payload(side,amount,rules,bid,ask,fee,now)


def close_remaining(config,api,journal):
    worker=Worker(config,api,journal)
    settle(worker)
    qty,cost=journal.position()
    rules,bid,ask,fee=worker.snapshot()
    if qty*bid >= number(rules['lotSizeFilter']['minOrderAmt'],True):
        payload=worker.payload('Sell',min(qty,api.available('Sell')),rules,bid,ask,fee,int(time.time()))
        worker.submit(payload,int(time.time()))
        settle(worker)
        qty,cost=journal.position()
        _,bid,_,_=worker.snapshot()
        if qty*bid >= number(rules['lotSizeFilter']['minOrderAmt'],True):
            raise Halt('Tradable test position remains; preserve journal')
    return qty,cost


def exit_case(config,api,directory,kind):
    journal=Journal(str(Path(directory)/('exit-'+kind+'.sqlite3')),config,api.identity())
    try:
        journal.db.execute('CREATE TABLE IF NOT EXISTS lifecycle(id INTEGER PRIMARY KEY CHECK(id=1), stage TEXT)')
        journal.db.execute("INSERT OR IGNORE INTO lifecycle VALUES(1,'NEW')")
        stage=journal.db.execute('SELECT stage FROM lifecycle').fetchone()[0]
        if stage=='DONE':
            print('Testnet '+kind+' exit: previously completed; no new orders',flush=True)
            return
        if stage!='NEW': raise Halt('Prior lifecycle intent needs inspection; no automatic retry')
        worker=Worker(config,api,journal)
        if journal.pending() or journal.position()!=(D(0),D(0)):
            raise Halt('Unexpected test holdings')
        rules,bid,ask,fee=worker.snapshot()
        payload=worker.payload('Buy',min(number(config.order_usdt),D('15'),api.available('Buy')),rules,bid,ask,fee,int(time.time()))
        journal.db.execute("UPDATE lifecycle SET stage='BUY_INTENT' WHERE id=1")
        worker.submit(payload,int(time.time()));settle(worker)
        if journal.position()[0]<=0:raise Halt('Test buy unfilled')
        triggered=TriggeredWorker(config,api,journal,kind)
        result=triggered.tick(int(time.time()))
        if not triggered.triggered or result.get('side')!='Sell':
            raise Halt('Expected exit path did not submit a sell')
        settle(worker)
        qty,cost=close_remaining(config,api,journal)
        journal.db.execute("UPDATE lifecycle SET stage='DONE' WHERE id=1")
        print(json.dumps({'testnet_exit_case':kind,'status':'PASSED',
            'trigger_source':'synthetic price for decision only; real Testnet quotes for order prices',
            'real_testnet_sell_fill':True,'remaining_test_btc':str(qty),
            'profitability_verified':False,'mainnet_orders_submitted':0}),flush=True)
    finally:journal.db.close()


def process_case(config,api,directory,config_path):
    root=Path(directory)/'process-control'
    root.mkdir(exist_ok=True)
    marker=root/'completed.json'
    if marker.exists():
        print('Testnet process control: previously completed',flush=True);return
    intent=root/'started.json'
    if intent.exists():raise Halt('Prior process-control test needs inspection')
    if config.environment!='testnet':raise Halt('Process tests refuse mainnet')
    initial=Supervisor(config_path,str(root),'')
    # This grant exists only inside the isolated Testnet test process. It never
    # changes the production worker's release environment or mainnet controls.
    supervisor=Supervisor(config_path,str(root),initial.digest)
    old_key=os.environ.get('BYBIT_API_KEY');old_secret=os.environ.get('BYBIT_API_SECRET')
    os.environ['BYBIT_API_KEY']=os.environ['BYBIT_TESTNET_API_KEY']
    os.environ['BYBIT_API_SECRET']=os.environ['BYBIT_TESTNET_API_SECRET']
    try:
        intent.write_text(json.dumps({'state':'START_INTENT'}))
        supervisor.apply({'action':'START','sequence':1,'worker_id':supervisor.worker_id,'config_digest':supervisor.digest})
        time.sleep(3)
        if supervisor.report()['state']!='RUNNING':raise Halt('Testnet child did not remain running')
        supervisor.apply({'action':'STOP','sequence':2})
        if supervisor.report()['state']!='STOPPED':raise Halt('Testnet process did not stop')
        journal=Journal(str(root/'execution-journal.sqlite3'),config,api.identity())
        try:qty,cost=close_remaining(config,api,journal)
        finally:journal.db.close()
        marker.write_text(json.dumps({'start':'PASSED','stop':'PASSED'}))
        print(json.dumps({'testnet_process_start':'PASSED','testnet_process_stop':'PASSED',
                          'remaining_test_btc':str(qty),'mainnet_orders_submitted':0}),flush=True)
    finally:
        supervisor.stop()
        if old_key is None:os.environ.pop('BYBIT_API_KEY',None)
        else:os.environ['BYBIT_API_KEY']=old_key
        if old_secret is None:os.environ.pop('BYBIT_API_SECRET',None)
        else:os.environ['BYBIT_API_SECRET']=old_secret


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--directory',required=True)
    parser.add_argument('--testnet-orders',action='store_true')
    args=parser.parse_args()
    try:
        if not args.testnet_orders:raise Halt('Explicit Testnet test authorization required')
        config=Config(**json.loads(Path(args.config).read_text()))
        api=TestnetOnly(config,os.getenv('BYBIT_TESTNET_API_KEY'),os.getenv('BYBIT_TESTNET_API_SECRET'))
        with open(str(Path(args.directory)/'lifecycle.lock'),'a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            exit_case(config,api,args.directory,'profit')
            exit_case(config,api,args.directory,'loss')
            process_case(config,api,args.directory,args.config)
        return 0
    except (Halt,ValueError,TypeError,OSError) as error:
        print(json.dumps({'testnet_lifecycle':'HALTED','reason':str(error) if isinstance(error,Halt) else type(error).__name__,
                          'mainnet_orders_submitted':0}),flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
