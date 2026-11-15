"""Owner command broker. Worker acknowledgements determine actual state."""
import threading
import time

class ActivationControl:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.report = None
        self.desired = None
        self.sequence = 0

    def update(self, report):
        required = {'state','orders_enabled','worker_id','config_digest','environment','ready'}
        if not isinstance(report, dict) or set(report) != required:
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
        with self.lock:
            self.report = {**report, 'received_at':self.clock()}
            command = self.desired
            if (not command or command['worker_id'] != report['worker_id'] or
                    command['config_digest'] != report['config_digest']):
                self.desired = None
                return {'action':'STOP','sequence':self.sequence}
            return {'action':command['action'],'sequence':command['sequence'],
                    'worker_id':command['worker_id'],'config_digest':command['config_digest']}

    def command(self, action):
        with self.lock:
            r = self.report
            fresh = bool(r and self.clock()-r['received_at'] < 20)
            if action not in ('START','STOP'):
                raise ValueError('Unknown action')
            if action == 'START' and (not fresh or not r['ready'] or r['state'] != 'STOPPED'):
                raise ValueError('Worker must be fresh, stopped, and exchange-validated before Start')
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
                'can_activate':bool(fresh and r['ready'] and r['state']=='STOPPED'),
                'environment':r['environment'] if fresh else None,
                'requested':self.desired['action'] if self.desired else 'STOP'}
