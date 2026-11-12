import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from unittest.mock import Mock
from spot_accounting import SpotAccounting, AccountingError
from bybit_submission import SubmissionJournal, SubmissionError, submit_once
from test_bybit_submission import plan
from spot_preflight import plan_sell


def receipt(client='b1', side='Buy', qty='1', value='10', fees=None, status='Filled'):
    return {'final':True,'consistent':True,'symbol':'SOLUSDT','side':side,
            'client_id':client,'order_id':'exchange-'+client,'filled_qty':qty,
            'filled_value_usdt':value,'fees_by_currency':fees or {},
            'execution_ids':['execution-'+client] if Decimal(qty) else [],'outcome':status}


class AccountingTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:',isolation_level=None)
        self.a=SpotAccounting(self.db)
    def tearDown(self): self.db.close()
    def apply(self,r,reserve='10'):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.a.apply(r,buy_reserve=reserve)
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def test_buy_fee_reduces_held_coins_not_quote_cost(self):
        self.apply(receipt(fees={'SOL':'.001'}))
        self.assertEqual(self.a.position('SOLUSDT'),(Decimal('.999'),Decimal('10'),Decimal('10')))

    def test_sell_profit_includes_buy_and_sell_quote_fees(self):
        self.apply(receipt(fees={'USDT':'.01'}),reserve='10.02')
        self.apply(receipt('s1','Sell','1','11',{'USDT':'.011'}))
        self.assertEqual(self.a.position('SOLUSDT'),(0,0,0))
        r=self.a.report()
        self.assertEqual(Decimal(r['realized_pnl_usdt_before_unpriced_fees']),Decimal('.979'))
        self.assertEqual(Decimal(r['commission_estimate_usdt']),Decimal('.0979'))
        self.assertFalse(r['commission_charged'])

    def test_base_fee_on_sell_consumes_extra_holdings(self):
        self.apply(receipt(qty='2',value='10'))
        self.apply(receipt('s1','Sell','1','6',{'SOL':'.01'}))
        self.assertEqual(self.a.position('SOLUSDT')[0],Decimal('.99'))
        self.assertEqual(Decimal(self.a.report()['realized_pnl_usdt_before_unpriced_fees']),Decimal('.95'))

    def test_rejected_sell_preserves_holdings(self):
        self.apply(receipt())
        before=self.a.position('SOLUSDT')
        self.apply(receipt('s1','Sell','0','0',status='Rejected'))
        self.assertEqual(before,self.a.position('SOLUSDT'))

    def test_external_fee_kept_unpriced_no_false_net_profit(self):
        self.apply(receipt(fees={'MNT':'.01'}))
        self.apply(receipt('s1','Sell','1','11'))
        r=self.a.report()
        self.assertIsNone(r['commission_estimate_usdt'])
        self.assertEqual(r['unpriced_fees'][0]['currency'],'MNT')

    def test_loss_has_zero_commission(self):
        self.apply(receipt())
        self.apply(receipt('s1','Sell','1','9'))
        self.assertEqual(Decimal(self.a.report()['commission_estimate_usdt']),0)

    def test_duplicate_receipt_idempotent(self):
        r=receipt()
        self.apply(r)
        self.apply(r)
        self.assertEqual(self.a.position('SOLUSDT')[0],1)

    def test_reused_execution_under_new_order_rolls_back(self):
        r=receipt()
        self.apply(r)
        duplicate=receipt('b2')
        duplicate['execution_ids']=r['execution_ids']
        with self.assertRaises(AccountingError): self.apply(duplicate)
        self.assertEqual(self.a.position('SOLUSDT')[0],1)

    def test_oversell_rolls_back_and_preserves_position(self):
        self.apply(receipt())
        with self.assertRaises(AccountingError): self.apply(receipt('s1','Sell','2','22'))
        self.assertEqual(self.a.position('SOLUSDT')[0],1)

    def test_partial_sale_releases_proportional_reservation(self):
        self.apply(receipt())
        self.apply(receipt('s1','Sell','.4','4.4',status='PartiallyFilledCanceled'))
        self.assertEqual(self.a.position('SOLUSDT'),(Decimal('.6'),Decimal('6'),Decimal('6')))

    def test_negative_fee_rebate_is_not_dropped(self):
        self.apply(receipt(fees={'USDT':'-.01'}))
        self.assertEqual(self.a.position('SOLUSDT')[1],Decimal('9.99'))


class FullCycleTest(unittest.TestCase):
    def test_buy_sell_restart_and_allocation_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'live-foundations.sqlite')
            j=SubmissionJournal(path)
            writer=Mock()
            writer.submit.return_value={'orderId':'exchange-b1','orderLinkId':'b1'}
            submit_once(plan('b1',price='10'),j,writer,activated=True)
            j.finish(receipt(fees={'SOL':'.001'}))
            sell={'mode':'PLAN_ONLY','base_fee_reserve':'0',
                  'payload':dict(plan()['payload'],side='Sell',qty='.999',price='11',orderLinkId='s1')}
            writer.submit.return_value={'orderId':'exchange-s1','orderLinkId':'s1'}
            submit_once(sell,j,writer,activated=True)
            j.finish(receipt('s1','Sell','.999','10.989',{'USDT':'.010989'}))
            self.assertEqual(j.accounting.position('SOLUSDT')[0],0)
            self.assertEqual(j.accounting.committed(),0)
            expected=Decimal('10.989')-Decimal('.010989')-Decimal('10')
            self.assertEqual(Decimal(j.accounting.report()['realized_pnl_usdt_before_unpriced_fees']),expected)
            j.close()
            j=SubmissionJournal(path)
            try:
                self.assertEqual(submit_once(sell,j,writer,activated=True)['state'],'FINAL')
                self.assertEqual(writer.submit.call_count,2)
                self.assertTrue(j.claim(plan('b2'))[0])
            finally: j.close()

    def test_sell_planner_checks_bot_and_exchange_holdings(self):
        args=dict(instrument={'symbol':'SOLUSDT','baseCoin':'SOL','quoteCoin':'USDT','status':'Trading',
                 'lotSizeFilter':{'basePrecision':'.001','minOrderAmt':'5','maxLimitOrderQty':'100'},
                 'priceFilter':{'tickSize':'.01'}},instrument_at=100,bid='10',ask='10.01',quote_at=100,
                 now=101,spendable_base='1',balance_at=100,bot_owned_qty='1',requested_qty='.9',
                 base_fee_reserve_rate='.001',order_link_id='s1')
        self.assertEqual(plan_sell(**args)['payload']['side'],'Sell')
        for override in [{'bot_owned_qty':'.8'},{'spendable_base':'.8'},{'requested_qty':'.1'},
                         {'quote_at':90},{'base_fee_reserve_rate':'NaN'}]:
            with self.assertRaises(ValueError): plan_sell(**dict(args,**override))

if __name__ == '__main__': unittest.main()
