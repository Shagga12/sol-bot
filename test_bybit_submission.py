import hashlib
import hmac
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from bybit_submission import BybitSpotWriter, SubmissionJournal, SubmissionError, submit_once


def plan(client_id='cc-1', qty='1', price='9.99'):
    from decimal import Decimal
    value = Decimal(qty)*Decimal(price)
    return {'mode':'PLAN_ONLY', 'maximum_quote_with_fee_reserve':str(value+Decimal('.01')),
            'fee_reserve_usdt':'.01', 'payload':{'category':'spot', 'symbol':'SOLUSDT',
            'side':'Buy', 'orderType':'Limit', 'timeInForce':'IOC', 'isLeverage':0,
            'qty':qty, 'price':price, 'orderLinkId':client_id}}


def receipt(qty='1', status='Filled'):
    return {'final':True, 'consistent':True, 'client_id':'cc-1', 'order_id':'exchange-1',
            'symbol':'SOLUSDT', 'side':'Buy', 'filled_qty':qty,
            'filled_value_usdt':'9.99' if qty == '1' else '0', 'outcome':status}


class SubmissionTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name)/'intents.sqlite')
        self.journal = SubmissionJournal(self.path)
        self.writer = Mock()
        self.writer.submit.return_value = {'orderId':'exchange-1', 'orderLinkId':'cc-1'}

    def tearDown(self):
        self.journal.close()
        self.folder.cleanup()

    def submit(self, p=None):
        return submit_once(p or plan(), self.journal, self.writer, activated=True)

    def test_disabled_means_no_intent_and_no_transport(self):
        with self.assertRaises(SubmissionError): submit_once(plan(), self.journal, self.writer)
        self.assertEqual(self.journal.entries(), [])
        self.writer.submit.assert_not_called()

    def test_ack_is_not_a_fill(self):
        self.assertEqual(self.submit()['state'], 'ACKNOWLEDGED')
        self.assertEqual(self.journal.entries()[0]['state'], 'ACKNOWLEDGED')

    def test_intent_exists_before_network(self):
        def inspect(payload):
            self.assertEqual(self.journal.entries()[0]['state'], 'UNKNOWN')
            return {'orderId':'exchange-1','orderLinkId':'cc-1'}
        self.writer.submit.side_effect = inspect
        self.submit()

    def test_timeout_restart_and_duplicate_never_resend(self):
        self.writer.submit.side_effect = TimeoutError('fixture')
        self.assertEqual(self.submit()['state'], 'UNKNOWN')
        self.journal.close()
        self.journal = SubmissionJournal(self.path)
        self.assertEqual(self.submit()['state'], 'UNKNOWN')
        self.assertEqual(self.writer.submit.call_count, 1)

    def test_unknown_blocks_new_client_id(self):
        self.writer.submit.side_effect = TimeoutError()
        self.submit()
        with self.assertRaises(SubmissionError): self.submit(plan('cc-2'))
        self.assertEqual(self.writer.submit.call_count, 1)

    def test_changed_plan_cannot_reuse_id(self):
        self.submit()
        with self.assertRaises(SubmissionError): self.submit(plan(price='9.98'))

    def test_incorrect_ack_identity_remains_unknown(self):
        self.writer.submit.return_value = {'orderId':'exchange-2','orderLinkId':'other'}
        self.assertEqual(self.submit()['state'], 'UNKNOWN')

    def test_verified_rejection_releases_budget_and_replay_does_not_send(self):
        self.submit()
        self.journal.finish(receipt('0', 'Rejected'))
        self.assertEqual(self.journal.entries()[0]['reserve'], '0')
        self.assertEqual(self.submit()['state'], 'FINAL')
        self.assertEqual(self.writer.submit.call_count, 1)

    def test_filled_position_keeps_capital_reserved(self):
        self.submit()
        self.journal.finish(receipt())
        self.assertEqual(self.journal.entries()[0]['reserve'], '10.00')
        with self.assertRaises(SubmissionError): self.submit(plan('cc-2', qty='2'))

    def test_cumulative_cap_across_final_positions(self):
        self.submit()
        self.journal.finish(receipt())
        p = plan('cc-2', qty='1', price='10')
        with self.assertRaises(SubmissionError): self.submit(p)

    def test_unverified_or_wrong_receipt_cannot_release(self):
        self.submit()
        for r in [dict(receipt('0','Rejected'), final=False), dict(receipt('0','Rejected'), order_id='other')]:
            with self.assertRaises(SubmissionError): self.journal.finish(r)
        self.assertEqual(self.journal.entries()[0]['reserve'], '10.00')

    def test_receipt_cannot_exceed_limit_or_quantity(self):
        self.submit()
        for r in [dict(receipt(), filled_value_usdt='10'), dict(receipt(), filled_qty='2')]:
            with self.assertRaises(SubmissionError): self.journal.finish(r)

    def test_final_receipt_idempotent_but_cannot_change(self):
        self.submit()
        self.journal.finish(receipt())
        self.journal.finish(receipt())
        with self.assertRaises(SubmissionError): self.journal.finish(receipt('0','Cancelled'))

    def test_second_connection_cannot_double_claim(self):
        other = SubmissionJournal(self.path)
        try:
            self.journal.claim(plan())
            self.assertFalse(other.claim(plan())[0])
        finally: other.close()

    def test_margin_or_extra_fields_rejected(self):
        for update in [{'isLeverage':1}, {'category':'linear'}, {'triggerPrice':'1'}, {'side':'Sell'}]:
            p = plan()
            p['payload'].update(update)
            with self.assertRaises(SubmissionError): self.submit(p)
        self.writer.submit.assert_not_called()

    def test_disabled_writer_never_calls_opener(self):
        opener = Mock()
        writer = BybitSpotWriter('fixture-key','fixture-secret',opener=opener)
        with self.assertRaises(SubmissionError): writer.submit(plan()['payload'])
        opener.open.assert_not_called()

    def test_signed_exact_transmitted_json_and_no_retry(self):
        body = io.BytesIO(json.dumps({'retCode':0,'result':{'orderId':'exchange-1','orderLinkId':'cc-1'}}).encode())
        body.status = 200
        opener = Mock()
        opener.open.return_value = body
        writer = BybitSpotWriter('fixture-key','fixture-secret', enabled=True, opener=opener, clock=lambda:100)
        writer.submit(plan()['payload'])
        req = opener.open.call_args.args[0]
        expected = hmac.new(b'fixture-secret', b'100000fixture-key5000'+req.data, hashlib.sha256).hexdigest()
        self.assertEqual(req.get_header('X-bapi-sign'), expected)
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(req.full_url, 'https://api.bybit.com/v5/order/create')
        self.assertEqual(opener.open.call_count, 1)

    def test_http_or_exchange_error_is_unknown_without_secret_leak(self):
        for status, data in [(403, {}), (200, {'retCode':10014,'retMsg':'fixture-secret'})]:
            body = io.BytesIO(json.dumps(data).encode())
            body.status = status
            opener = Mock()
            opener.open.return_value = body
            writer = BybitSpotWriter('fixture-key','fixture-secret', enabled=True, opener=opener)
            with self.assertRaises(SubmissionError) as e: writer.submit(plan()['payload'])
            self.assertNotIn('fixture-secret', str(e.exception))
            self.assertEqual(opener.open.call_count, 1)

if __name__ == '__main__': unittest.main()
