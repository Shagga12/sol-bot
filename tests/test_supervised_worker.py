import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import Mock
from test_live import config
from capital_connect_v1.supervised_worker import Supervisor

class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.tmp.name)/'config.json')
        Path(self.path).write_text(json.dumps(asdict(config())))
        self.factory=Mock()
        self.factory.return_value.poll.return_value=None
        self.s=Supervisor(self.path,self.tmp.name,'',self.factory)
    def tearDown(self):self.tmp.cleanup()
    def command(self,seq=1):return {'action':'START','sequence':seq,'worker_id':self.s.worker_id,'config_digest':self.s.digest}
    def test_missing_release_cannot_spawn(self):
        with self.assertRaises(ValueError):self.s.apply(self.command())
        self.factory.assert_not_called()
    def test_start_stop_and_replay_do_not_duplicate_process(self):
        self.s.ready=True
        self.s.apply(self.command());self.s.apply(self.command())
        self.assertEqual(self.factory.call_count,1)
        self.assertTrue(self.s.report()['orders_enabled'])
        self.s.apply({'action':'STOP','sequence':2})
        self.factory.return_value.terminate.assert_called_once()
        self.assertFalse(self.s.report()['orders_enabled'])
        self.s.apply(self.command())
        self.assertEqual(self.factory.call_count,1)
    def test_different_worker_or_config_cannot_start(self):
        self.s.ready=True
        for field in ('worker_id','config_digest'):
            with self.assertRaises(ValueError):self.s.apply({**self.command(),field:'0'*64})
        self.factory.assert_not_called()
    def test_child_failure_is_sticky_and_never_auto_restarted(self):
        self.s.ready=True;self.s.apply(self.command())
        self.factory.return_value.poll.return_value=1
        self.assertEqual(self.s.report()['state'],'HALTED')
        with self.assertRaises(ValueError):self.s.apply(self.command(2))
        self.assertEqual(self.factory.call_count,1)
    def test_matching_release_is_bound_to_exact_configuration(self):
        good=Supervisor(self.path,self.tmp.name,self.s.digest,self.factory)
        self.assertTrue(good.ready)
        Path(self.path).write_text(json.dumps(asdict(config(order_usdt='9'))))
        changed=Supervisor(self.path,self.tmp.name,self.s.digest,self.factory)
        self.assertFalse(changed.ready)
