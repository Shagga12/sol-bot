import json
import os
from pathlib import Path
import tempfile
import unittest
from dataclasses import asdict
from unittest.mock import Mock, patch
from test_live import config
from capital_connect_v1.testnet_check import run_testnet_check

class TestnetIsolationTests(unittest.TestCase):
    def test_missing_testnet_credentials_never_uses_mainnet_keys(self):
        runner=Mock()
        with patch.dict(os.environ, {'BYBIT_API_KEY':'main-key','BYBIT_API_SECRET':'main-secret'}, clear=True):
            self.assertIsNone(run_testnet_check('/unused',runner))
        runner.assert_not_called()
    def test_child_uses_testnet_host_config_and_separate_journal(self):
        env={'BYBIT_API_KEY':'main-key','BYBIT_API_SECRET':'main-secret',
             'BYBIT_TESTNET_API_KEY':'test-key','BYBIT_TESTNET_API_SECRET':'test-secret',
             'CAPITAL_LIVE_CONFIG_JSON':json.dumps(asdict(config(environment='mainnet'))),
             'CAPITAL_EXECUTION_VALIDATED_CONFIG_SHA256':'not-inherited'}
        runner=Mock(return_value=Mock(returncode=0))
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,env,clear=True):
            self.assertEqual(run_testnet_check(directory,runner),0)
            args=runner.call_args.args[0]; child=runner.call_args.kwargs['env']
            self.assertEqual(args[3],'check')
            self.assertNotIn('--enable-orders',args)
            self.assertEqual(json.loads(Path(args[5]).read_text())['environment'],'testnet')
            self.assertIn('testnet-validation', args[7])
            self.assertEqual(child['BYBIT_API_KEY'],'test-key')
            self.assertNotIn('CAPITAL_EXECUTION_VALIDATED_CONFIG_SHA256',child)
            self.assertEqual(os.environ['BYBIT_API_KEY'],'main-key')

class TestnetOrderGuardTests(unittest.TestCase):
    def test_order_transport_refuses_mainnet_before_network(self):
        from capital_connect_v1.testnet_exchange import TestnetOnly
        from capital_connect_v1.live import Halt
        with self.assertRaises(Halt):
            TestnetOnly(config(environment='mainnet'),'fake','fake')
    def test_only_testnet_host_is_selected(self):
        from capital_connect_v1.testnet_exchange import TestnetOnly
        api=TestnetOnly(config(),'fake-key','fake-secret')
        self.assertEqual(api.base,'https://api-testnet.bybit.com')
    def test_explicit_flag_runs_two_separate_testnet_processes(self):
        env={'BYBIT_TESTNET_API_KEY':'test-key','BYBIT_TESTNET_API_SECRET':'test-secret',
             'CAPITAL_LIVE_CONFIG_JSON':json.dumps(asdict(config(environment='mainnet'))),
             'CAPITAL_TESTNET_ORDER_TESTS':'run'}
        runner=Mock(return_value=Mock(returncode=0))
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,env,clear=True):
            self.assertEqual(run_testnet_check(directory,runner),0)
        self.assertEqual(runner.call_count,3)
        for call in runner.call_args_list[1:]:
            self.assertIn('--testnet-orders',call.args[0])
            self.assertEqual(call.kwargs['env']['BYBIT_API_KEY'],'test-key')

class TestnetPhaseTests(unittest.TestCase):
    def test_reopen_reconciles_both_sides_and_rerun_cannot_duplicate(self):
        from test_live import Fake, fill
        from capital_connect_v1.live import D
        from capital_connect_v1.testnet_exchange import phase
        class Filled(Fake):
            base='https://api-testnet.bybit.com'
            def identity(self):return 'test-user'
            def request(self,endpoint,params=None,write=False):
                result=super().request(endpoint,params,write)
                if write:
                    q=D(params['qty']); v=q*D(params['price'])
                    self.order={'orderId':'exchange-order','orderLinkId':params['orderLinkId'],
                        'symbol':'BTCUSDT','side':params['side'],'orderStatus':'Filled',
                        'cumExecQty':str(q),'cumExecValue':str(v)}
                    currency='BTC' if params['side']=='Buy' else 'USDT'
                    fee=q*D('.001') if currency=='BTC' else v*D('.001')
                    self.fills=[fill(params['side'],str(q),str(v),str(fee),currency)]
                return result
        api=Filled()
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(phase(config(),api,directory,'buy'),0)
            self.assertEqual(phase(config(),api,directory,'close'),0)
            self.assertEqual(len(api.writes),2)
            self.assertEqual(phase(config(),api,directory,'buy'),0)
            self.assertEqual(phase(config(),api,directory,'close'),0)
            self.assertEqual(len(api.writes),2)
