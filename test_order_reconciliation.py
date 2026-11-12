import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from diagnostics import ConnectionError
from order_reconciliation import reconcile, ReceiptJournal


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.order = dict(symbol='SOLUSDT', orderLinkId='cc-1', orderId='exchange-1', side='Buy',
                          orderStatus='Filled', createdTime='100', updatedTime='200',
                          cumExecQty='1', cumExecValue='10')
        self.fill = dict(symbol='SOLUSDT', orderId='exchange-1', side='Buy', execType='Trade',
                         execId='fill-1', execQty='1', execValue='10', execFee='.001',
                         feeCurrency='SOL', execTime='150')

    def run_receipt(self, orders=None, fills=None):
        fetch = Mock(side_effect=[{'list': [self.order] if orders is None else orders},
                                  {'list': [self.fill] if fills is None else fills}])
        return reconcile('SOLUSDT', 'cc-1', 'fixture', 'fixture', start_ms=1, end_ms=300, fetch=fetch)

    def test_base_asset_fee_kept_in_its_own_currency(self):
        r = self.run_receipt()
        self.assertTrue(r['final'])
        self.assertEqual(r['fees_by_currency'], {'SOL': '0.001'})
        self.assertEqual(r['filled_qty'], '1')

    def test_sell_fee_and_rebate_preserved(self):
        self.order['side'] = self.fill['side'] = 'Sell'
        self.fill.update(feeCurrency='USDT', execFee='-.01')
        self.assertEqual(self.run_receipt()['fees_by_currency'], {'USDT': '-0.01'})

    def test_duplicate_fill_not_counted_twice(self):
        r = self.run_receipt(fills=[self.fill, dict(self.fill)])
        self.assertTrue(r['final'])
        self.assertEqual(r['filled_qty'], '1')

    def test_conflicting_duplicate_stops(self):
        with self.assertRaises(ConnectionError):
            self.run_receipt(fills=[self.fill, dict(self.fill, execQty='2')])

    def test_filled_order_without_executions_not_final(self):
        self.assertFalse(self.run_receipt(fills=[])['final'])

    def test_acknowledgement_not_a_completed_trade(self):
        self.order.update(orderStatus='New', cumExecQty='0', cumExecValue='0')
        self.assertFalse(self.run_receipt(fills=[])['final'])

    def test_cancelled_partial_fill_preserved(self):
        self.order.update(orderStatus='PartiallyFilledCanceled')
        self.assertTrue(self.run_receipt()['final'])
        self.assertEqual(self.run_receipt()['filled_qty'], '1')

    def test_wrong_order_cannot_be_reconciled(self):
        self.fill['orderId'] = 'other-order'
        with self.assertRaises(ConnectionError): self.run_receipt()

    def test_missing_fee_currency_stops(self):
        del self.fill['feeCurrency']
        with self.assertRaises(ConnectionError): self.run_receipt()

    def test_ambiguous_order_identity_stops(self):
        with self.assertRaises(ConnectionError): self.run_receipt(orders=[self.order, self.order])

    def test_complete_execution_window_required(self):
        self.order['createdTime'] = '0'
        with self.assertRaises(ConnectionError): self.run_receipt()

    def test_pagination_collects_all_fills(self):
        self.order.update(cumExecQty='2', cumExecValue='20')
        fetch = Mock(side_effect=[{'list': [self.order]}, {'list': [self.fill], 'nextPageCursor': 'next'},
                                  {'list': [dict(self.fill, execId='fill-2')]}])
        r = reconcile('SOLUSDT', 'cc-1', 'fixture', 'fixture', start_ms=1, end_ms=300, fetch=fetch)
        self.assertTrue(r['final'])
        self.assertEqual(fetch.call_args_list[-1].args[1]['cursor'], 'next')

    def test_repeated_cursor_stops(self):
        fetch = Mock(side_effect=[{'list': [self.order]}, {'list': [], 'nextPageCursor': 'x'},
                                  {'list': [], 'nextPageCursor': 'x'}])
        with self.assertRaises(ConnectionError):
            reconcile('SOLUSDT', 'cc-1', 'fixture', 'fixture', start_ms=1, end_ms=300, fetch=fetch)

    def test_order_history_fallback_after_exchange_restart(self):
        fetch = Mock(side_effect=[{'list': []}, {'list': [self.order]}, {'list': [self.fill]}])
        r = reconcile('SOLUSDT', 'cc-1', 'fixture', 'fixture', start_ms=1, end_ms=300, fetch=fetch)
        self.assertTrue(r['final'])
        self.assertEqual(fetch.call_args_list[1].args[0], '/v5/order/history')

    def test_absent_order_stays_unknown(self):
        fetch = Mock(return_value={'list': []})
        r = reconcile('SOLUSDT', 'cc-1', 'fixture', 'fixture', start_ms=1, end_ms=300, fetch=fetch)
        self.assertEqual(r['outcome'], 'UNKNOWN')
        self.assertFalse(r['final'])

    def test_receipt_durable_and_duplicate_save_idempotent(self):
        receipt = self.run_receipt()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'audit.sqlite')
            journal = ReceiptJournal(path)
            journal.save(receipt)
            journal.save(receipt)
            journal.close()
            journal = ReceiptJournal(path)
            try: self.assertEqual(journal.all(), [receipt])
            finally: journal.close()

    def test_transport_error_propagates_without_retry_or_resubmit(self):
        fetch = Mock(side_effect=ConnectionError('fixture timeout'))
        with self.assertRaises(ConnectionError):
            reconcile('SOLUSDT', 'cc-1', 'fixture', 'fixture', start_ms=1, end_ms=300, fetch=fetch)
        self.assertEqual(fetch.call_count, 1)

    def test_malformed_fee_never_treated_as_zero(self):
        for value in ['NaN', 'Infinity', None]:
            self.fill['execFee'] = value
            with self.assertRaises(ConnectionError): self.run_receipt()

if __name__ == '__main__': unittest.main()
