import unittest
from decimal import Decimal as D
from test_live import config,RULES
from capital_connect_v1.live import Halt
from capital_connect_v1.protection import attach_protection
from capital_connect_v1.testnet_protection import probe

class ProtectionTests(unittest.TestCase):
    def base(self):return {'category':'spot','symbol':'BTCUSDT','side':'Buy','orderType':'Limit','price':'60000','qty':'.0002'}
    def test_attached_market_exits_have_valid_direction_and_conservative_fee_target(self):
        p=attach_protection(self.base(),config(),RULES,D('.001'))
        self.assertLess(D(p['stopLoss']),D(p['price']))
        self.assertGreater(D(p['takeProfit']),D(p['price']))
        self.assertEqual(p['tpOrderType'],'Market')
        self.assertEqual(p['slOrderType'],'Market')
        net=D(p['takeProfit'])*(1-D('.001'))**2/(D('60000')*(1+D('.001')))-1
        self.assertGreaterEqual(net,D('.04'))
    def test_cannot_attach_to_derivatives_or_sell(self):
        for changes in ({'category':'linear'},{'side':'Sell'},{'orderType':'Market'}):
            with self.assertRaises(Halt):attach_protection({**self.base(),**changes},config(),RULES,D('.001'))
    def test_fee_leaves_no_valid_stop_fails_closed(self):
        with self.assertRaises(Halt):attach_protection(self.base(),config(),RULES,D('.05'))
    def test_probe_refuses_mainnet_before_account_calls(self):
        class API:base='https://api.bybit.com'
        with self.assertRaises(Halt):probe(config(environment='mainnet'),API(),'/unused','create')
