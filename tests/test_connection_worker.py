import unittest
from unittest.mock import patch, MagicMock
from capital_connect_v1.connection_worker import run

class ConnectionWorkerTests(unittest.TestCase):
    def test_missing_setup_never_calls_exchange(self):
        with patch.dict('os.environ', {}, clear=True), patch('capital_connect_v1.connection_worker.check') as check, patch('capital_connect_v1.connection_worker.threading.Event') as event, patch('capital_connect_v1.connection_worker.signal.signal'):
            run()
            check.assert_not_called()
    def test_checks_without_activation_flags(self):
        env = {'CAPITAL_LIVE_CONFIG_JSON':'{}','BYBIT_API_KEY':'fake','BYBIT_API_SECRET':'fake'}
        with patch.dict('os.environ',env,clear=True), patch('capital_connect_v1.connection_worker.prepare_config', return_value='/var/data/config.json'), patch('capital_connect_v1.connection_worker.check',return_value=0) as check, patch('capital_connect_v1.connection_worker.threading.Event'), patch('capital_connect_v1.connection_worker.signal.signal'):
            run()
            args=check.call_args.args[0]
            self.assertEqual(args[0],'check')
            self.assertNotIn('--enable-orders',args)
            self.assertNotIn('--acknowledge-real-money',args)
