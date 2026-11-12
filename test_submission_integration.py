import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from bybit_submission import SubmissionJournal, BybitSpotWriter, submit_once
from spot_preflight import plan_buy
from order_reconciliation import reconcile


class IntegrationTest(unittest.TestCase):
    def test_plan_ack_partial_cancel_and_restart_with_fixture_exchange(self):
        p = plan_buy(instrument={'symbol':'SOLUSDT','baseCoin':'SOL','quoteCoin':'USDT',
                      'status':'Trading','lotSizeFilter':{'basePrecision':'.001',
                      'minOrderAmt':'5','maxLimitOrderQty':'100'},'priceFilter':{'tickSize':'.01'}},
                     instrument_at=100,bid='10',ask='10',quote_at=100,now=101,
                     available_usdt='5.5241',balance_at=100,committed_usdt='0',budget='5.50',
                     fee_reserve_rate='.001',order_link_id='cc-fixture')
        writer = Mock()
        writer.submit.return_value = {'orderId':'order-fixture','orderLinkId':'cc-fixture'}
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'submission.sqlite')
            j = SubmissionJournal(path)
            self.assertEqual(submit_once(p,j,writer,activated=True)['state'],'ACKNOWLEDGED')
            fetch = Mock(side_effect=[{'list':[{'symbol':'SOLUSDT','orderLinkId':'cc-fixture',
                     'orderId':'order-fixture','side':'Buy','orderStatus':'PartiallyFilledCanceled',
                     'createdTime':'100','updatedTime':'200','cumExecQty':'.5','cumExecValue':'5'}]},
                     {'list':[{'symbol':'SOLUSDT','orderId':'order-fixture','side':'Buy','execType':'Trade',
                     'execId':'fill-fixture','execQty':'.5','execValue':'5','execFee':'.0005',
                     'feeCurrency':'SOL','execTime':'150'}]}])
            r = reconcile('SOLUSDT','cc-fixture','fixture-key','fixture-secret',start_ms=1,end_ms=300,fetch=fetch)
            self.assertTrue(r['final'])
            self.assertEqual(r['fees_by_currency'],{'SOL':'0.0005'})
            j.finish(r)
            j.close()
            j = SubmissionJournal(path)
            try:
                self.assertEqual(submit_once(p,j,writer,activated=True)['state'],'FINAL')
                self.assertEqual(writer.submit.call_count,1)
                self.assertEqual(j.entries()[0]['reserve'],p['maximum_quote_with_fee_reserve'])
            finally: j.close()

    def test_default_transport_has_no_redirect_handler(self):
        writer = BybitSpotWriter('fixture','fixture')
        handler = next(h for h in writer.opener.handlers if h.__class__.__name__ == 'NoRedirect')
        self.assertIsNone(handler.redirect_request(None,None,302,'fixture',{},'https://example.invalid'))

if __name__ == '__main__': unittest.main()
