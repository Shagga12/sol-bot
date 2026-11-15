import unittest
from decimal import Decimal
from trader_platform.domain import CommissionBook,Invalid,Locked,Release,UnconfiguredCustody,UnconfiguredExecution,order_review

class Commissions(unittest.TestCase):
    def test_ten_percent_after_fees_not_deposits_or_unrealized_values(self):
        b=CommissionBook();self.assertEqual(b.settle('closed-1','98'),Decimal('9.80'));self.assertEqual(b.due(),Decimal('9.80'))
    def test_losses_recovered_and_previous_fees_not_charged_twice(self):
        b=CommissionBook()
        self.assertEqual(b.settle('1','-20'),0)
        self.assertEqual(b.settle('2','15'),0)
        self.assertEqual(b.settle('3','15'),Decimal('1'))
        self.assertEqual(b.settle('4','-5'),0)
        self.assertEqual(b.settle('5','5'),0)
        self.assertEqual(b.settle('6','10'),Decimal('1'))
        self.assertEqual(b.due(),Decimal('2.00'))
    def test_duplicate_and_conflicting_settlement(self):
        b=CommissionBook();b.settle('fill','100');self.assertEqual(b.settle('fill','100.0'),0)
        with self.assertRaises(Invalid):b.settle('fill','101')
        self.assertEqual(b.accrued,10)
    def test_subcent_accrual_is_preserved_until_total_can_be_collected(self):
        b=CommissionBook()
        for i in range(10):b.settle(str(i),'.01')
        self.assertEqual(b.due(),Decimal('.01'));self.assertEqual(b.accrued,Decimal('.010'))
    def test_tenant_books_are_separate(self):
        a,b=CommissionBook(),CommissionBook();a.settle('same-id','100');b.settle('same-id','-50')
        self.assertEqual(a.due(),10);self.assertEqual(b.due(),0)
    def test_no_collection_and_invalid_numbers(self):
        b=CommissionBook()
        for n in ('NaN','Infinity','0.000000001','1e20'):
            with self.assertRaises(Invalid):b.settle(n,n)
        with self.assertRaises(Locked):b.collect('anything')

class Gates(unittest.TestCase):
    def test_missing_approval_or_provider_never_enables_custody(self):
        self.assertFalse(Release(onboarding_enabled=True,funding_enabled=True,trading_enabled=True).permits('onboarding'))
        self.assertFalse(Release('ref',True,True,True).permits('funding'))
        self.assertFalse(Release('ref',True,True,True,'provider').permits('trading'))
    def test_preparation_cannot_submit_even_if_all_flags_are_edited(self):
        r=Release('ref',True,True,True,'provider','release')
        self.assertFalse(r.public()['trading_enabled']);self.assertFalse(r.public()['funding_enabled'])
        with self.assertRaises(Locked):UnconfiguredExecution().submit('Buy')
        with self.assertRaises(Locked):UnconfiguredCustody().deposit_address('user','USDT','network')
    def test_buy_sell_review_is_bounded_and_never_executable(self):
        for side in ('Buy','Sell'):
            r=order_review({'status':'pending','order_limit_usdt':'15'},{'side':side,'symbol':'BTCUSDT','amount_usdt':'15'})
            self.assertFalse(r['can_submit']);self.assertEqual(r['orders_submitted'],0)
        with self.assertRaises(Invalid):order_review({'status':'approved','order_limit_usdt':'15'},{'side':'Buy','symbol':'BTCUSDT','amount_usdt':'15.01'})
