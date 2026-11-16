import tempfile
import unittest
from decimal import Decimal as D
from test_live import config, Fake, NOW
from capital_connect_v1.live import Journal, Halt
from capital_connect_v1.testnet_lifecycle import TriggeredWorker

class LifecycleGuardTests(unittest.TestCase):
    def test_mainnet_refused(self):
        fake=Fake();fake.base='https://api.bybit.com'
        with self.assertRaises(Halt):TriggeredWorker(config(environment='mainnet'),fake,None,'profit')
    def test_both_synthetic_decisions_submit_only_real_quote_bounded_sell(self):
        for kind in ('profit','loss'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                fake=Fake();fake.base='https://api-testnet.bybit.com'
                journal=Journal(root+'/test.sqlite3',config(),'test-user')
                try:
                    journal.db.execute("UPDATE live_position SET qty='.0002',cost='12' WHERE id=1")
                    worker=TriggeredWorker(config(),fake,journal,kind)
                    result=worker.tick(NOW)
                    self.assertTrue(worker.triggered)
                    self.assertEqual(result['side'],'Sell')
                    order=fake.writes[0]
                    self.assertLessEqual(D(order['price']),fake.bid)
                    self.assertEqual(order['category'],'spot')
                    self.assertEqual(order['isLeverage'],0)
                    self.assertLessEqual(D(order['qty']),D('.0002'))
                finally:journal.db.close()
