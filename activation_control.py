"""Owner command broker. Worker acknowledgements determine actual state."""
import threading
import time
from decimal import Decimal, InvalidOperation

class ActivationControl:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.report = None
        self.desired = None
        self.sequence = 0

    def update(self, report):
        required = {'state','orders_enabled','worker_id','config_digest','environment','ready'}
        if not isinstance(report, dict) or not required <= set(report) or set(report)-required-{'limits','execution'}:
            raise ValueError('Invalid worker status')
        if report['state'] not in ('STOPPED','STARTING','RUNNING','HALTED'):
            raise ValueError('Invalid worker state')
        if type(report['orders_enabled']) is not bool or type(report['ready']) is not bool:
            raise ValueError('Invalid flags')
        if report['orders_enabled'] != (report['state'] == 'RUNNING'):
            raise ValueError('Inconsistent execution status')
        if report['environment'] not in ('mainnet','testnet'):
            raise ValueError('Invalid environment')
        for key in ('worker_id','config_digest'):
            value = report[key]
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Invalid worker binding')
        limits = report.get('limits')
        if limits is not None:
            keys={'symbol','capital_usdt','order_usdt','daily_loss_usdt','stop_loss_fraction','take_profit_fraction','slippage_percent'}
            if not isinstance(limits,dict) or set(limits)!=keys or limits['symbol'] not in ('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'):
                raise ValueError('Invalid execution limits')
            for key in keys-{'symbol'}:
                value=limits[key]
                if not isinstance(value,str) or len(value)>24: raise ValueError('Invalid execution limit')
                try: number=Decimal(value)
                except InvalidOperation: raise ValueError('Invalid execution limit') from None
                if not number.is_finite() or number<=0: raise ValueError('Invalid execution limit')
        execution=report.get('execution')
        if execution is not None:
            keys={'owned_qty','cost_usdt','realized_pnl_usdt','pending_entries','active_protections'}
            if not isinstance(execution,dict) or set(execution)!=keys: raise ValueError('Invalid execution summary')
            for key in ('owned_qty','cost_usdt','realized_pnl_usdt'):
                value=execution[key]
                if not isinstance(value,str) or len(value)>100:raise ValueError('Invalid execution number')
                try:number=Decimal(value)
                except InvalidOperation:raise ValueError('Invalid execution number') from None
                if not number.is_finite() or (key!='realized_pnl_usdt' and number<0):raise ValueError('Invalid execution number')
            if any(type(execution[key]) is not int or not 0<=execution[key]<=500 for key in ('pending_entries','active_protections')):
                raise ValueError('Invalid execution count')
        with self.lock:
            self.report = {**report, 'received_at':self.clock()}
            command = self.desired
            if (not command or command['worker_id'] != report['worker_id'] or
                    command['config_digest'] != report['config_digest']):
                self.desired = None
                return {'action':'STOP','sequence':self.sequence}
            return {'action':command['action'],'sequence':command['sequence'],
                    'worker_id':command['worker_id'],'config_digest':command['config_digest']}

    def command(self, action, acknowledge_real_money=False, config_digest=None):
        with self.lock:
            r = self.report
            fresh = bool(r and self.clock()-r['received_at'] < 20)
            if action not in ('START','STOP'):
                raise ValueError('Unknown action')
            if action == 'START' and (not fresh or not r['ready'] or r['state'] != 'STOPPED'):
                raise ValueError('Worker must be fresh, stopped, and exchange-validated before Start')
            if action == 'START':
                if config_digest is not None and config_digest!=r['config_digest']:
                    raise ValueError('Saved configuration changed; review it again')
                if r['environment']=='mainnet' and (acknowledge_real_money is not True or config_digest!=r['config_digest'] or not r.get('limits')):
                    raise ValueError('Review saved limits and explicitly acknowledge real-money trading')
            self.sequence += 1
            self.desired = ({'action':action,'sequence':self.sequence,
                'worker_id':r['worker_id'],'config_digest':r['config_digest']} if r else None)
            return {'accepted':True,'requested':action,'sequence':self.sequence,
                    'note':'Await worker acknowledgement. Stop does not sell holdings.'}

    def status(self):
        with self.lock:
            r = self.report
            fresh = bool(r and self.clock()-r['received_at'] < 20)
            return {'control_connected':fresh, 'state':r['state'] if fresh else 'NOT_CONNECTED',
                'real_trading_active':bool(fresh and r['orders_enabled'] and r['environment']=='mainnet'),
                'orders_running':bool(fresh and r['orders_enabled']),
                'can_activate':bool(fresh and r['ready'] and r['state']=='STOPPED' and (r['environment']!='mainnet' or r.get('limits'))),
                'config_digest':r['config_digest'] if fresh else None,
                'limits':r.get('limits') if fresh else None,
                'execution':r.get('execution') if fresh else None,
                'environment':r['environment'] if fresh else None,
                'requested':self.desired['action'] if self.desired else 'STOP'}
