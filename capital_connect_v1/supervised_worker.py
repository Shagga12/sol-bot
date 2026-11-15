"""Owner-controlled process supervisor. No orders until a validated release and owner Start.
The release digest is provisioned only after exchange tests; it is absent by default.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import sqlite3
from decimal import Decimal
from dataclasses import asdict
from urllib.request import Request, build_opener
from .live import Config, NoRedirect

class Supervisor:
    def __init__(self, config_path, directory, release_digest, popen=subprocess.Popen):
        self.path = config_path
        self.directory = directory
        raw = json.loads(Path(config_path).read_text())
        self.config = Config(**raw)
        self.digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',',':')).encode()).hexdigest()
        self.worker_id = secrets.token_hex(32)
        self.ready = bool(release_digest and secrets.compare_digest(release_digest, self.digest))
        self.child = None
        self.state = 'STOPPED'
        self.sequence = 0
        self.popen = popen

    def report(self):
        if self.child is not None and self.child.poll() is not None:
            self.child = None
            self.state = 'HALTED'
            self.ready = False  # Never conceal a halt with an automatic restart.
        return {'worker_id':self.worker_id,'config_digest':self.digest,
                'environment':self.config.environment,'state':self.state,
                'orders_enabled':self.state == 'RUNNING','ready':self.ready,
                'limits':{key:value for key,value in asdict(self.config).items() if key!='environment'},
                'execution':self.execution_summary()}

    def execution_summary(self):
        path=Path(self.directory)/'execution-journal.sqlite3'
        if not path.exists(): return None
        db=None
        try:
            db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
            db.row_factory=sqlite3.Row
            db.execute('BEGIN')
            binding=json.loads(db.execute('SELECT binding FROM live_meta WHERE id=1').fetchone()[0])
            if binding['config']!=asdict(self.config):return None
            position=db.execute('SELECT qty,cost FROM live_position WHERE id=1').fetchone()
            pnl=sum((Decimal(r[0]) for r in db.execute('SELECT pnl FROM live_orders WHERE terminal=1')),Decimal(0))
            return {'owned_qty':position['qty'],'cost_usdt':position['cost'],
                    'realized_pnl_usdt':str(pnl),
                    'pending_entries':db.execute("SELECT COUNT(*) FROM live_orders WHERE terminal=0 AND side='Buy'").fetchone()[0],
                    'active_protections':db.execute("SELECT COUNT(*) FROM live_protection WHERE state='ACTIVE'").fetchone()[0]}
        except (sqlite3.Error,ValueError,KeyError,TypeError,IndexError):
            return None
        finally:
            if db is not None:db.close()

    def stop(self):
        if self.child is not None:
            self.child.terminate()
            try:
                self.child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=10)
            self.child = None
        if self.state != 'HALTED': self.state = 'STOPPED'

    def apply(self, command):
        if not isinstance(command,dict): raise ValueError('Invalid command')
        if command.get('action') == 'STOP':
            if type(command.get('sequence')) is int:
                self.sequence = max(self.sequence, command['sequence'])
            self.stop()
            return
        if (command.get('action') != 'START' or not self.ready or self.state == 'HALTED' or
            command.get('worker_id') != self.worker_id or command.get('config_digest') != self.digest):
            raise ValueError('Start is not authorized for this validated worker/configuration')
        sequence = command.get('sequence')
        if type(sequence) is not int or sequence <= 0: raise ValueError('Invalid sequence')
        if sequence <= self.sequence: return
        if self.child is not None: return
        self.sequence = sequence
        argv = [sys.executable,'-m','capital_connect_v1.live','run','--config',self.path,
                '--db',str(Path(self.directory)/'execution-journal.sqlite3'),'--enable-orders']
        if self.config.environment == 'mainnet': argv.append('--acknowledge-real-money')
        # Reconciliation and strict spot permissions are checked again by live.run.
        # A Start request is an authorization, not a promise of an order or fill.
        self.child = self.popen(argv)
        self.state = 'RUNNING'


def supervise(stop, config_path, directory):
    supervisor = Supervisor(config_path, directory, os.getenv('CAPITAL_EXECUTION_VALIDATED_CONFIG_SHA256',''))
    token = os.getenv('CAPITAL_LIVE_REPORT_TOKEN','')
    print(json.dumps({'control_connected':True,'execution_release_validated':supervisor.ready,
                      'orders_enabled':False,'config_digest':supervisor.digest}), flush=True)
    try:
        while not stop.is_set():
            try:
                if not token: raise ValueError('Control credential missing')
                req = Request('https://capital-connect-preflight.onrender.com/api/live/worker',
                    data=json.dumps(supervisor.report()).encode(), method='POST',
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                with build_opener(NoRedirect).open(req, timeout=8) as response:
                    command = json.load(response)
                supervisor.apply(command)
                print('Execution control status delivered; state='+supervisor.state, flush=True)
            except Exception:
                supervisor.stop()
                supervisor.state='HALTED'
                supervisor.ready=False
                print('Execution control unavailable; worker halted; no automatic restart', flush=True)
            if stop.wait(5): break
    finally:
        supervisor.stop()
