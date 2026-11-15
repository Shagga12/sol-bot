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
