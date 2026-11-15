import unittest,re
from pathlib import Path
from random import Random
from decimal import Decimal
from trader_platform.domain import CommissionBook

class Contracts(unittest.TestCase):
    def test_all_javascript_targets_exist_and_no_browser_storage_tokens(self):
        root=Path(__file__).parents[1]/'web';html=(root/'index.html').read_text();js=(root/'portal.js').read_text()
        for name in re.findall(r"el\('([^']+)'\)",js):self.assertIn('id="'+name+'"',html)
        self.assertNotIn('localStorage',js);self.assertNotIn('sessionStorage',js);self.assertNotIn('innerHTML',js)
    def test_schemas_have_rls_and_no_frontend_financial_write_grants(self):
        sql=(Path(__file__).parents[1]/'schema'/'preparation.sql').read_text()
        for name in ('release','profiles','wallet_entries','orders','commission_state','commissions','audit'):
            self.assertIn('alter table public.cc_trader_'+name+' enable row level security',sql)
        self.assertNotRegex(sql,r'grant\s+(insert|all)\s+on\s+public\.cc_trader_')
        self.assertIn('from public,anon,authenticated,service_role',sql)
        self.assertIn('set search_path=\'\'',sql)
    def test_random_walk_accrues_exactly_ten_percent_of_lifetime_profit_peak(self):
        rng=Random(17);b=CommissionBook();net=Decimal(0);peak=Decimal(0)
        for i in range(1000):
            value=Decimal(rng.randrange(-10000,10001))/100
            b.settle(str(i),str(value));net+=value;peak=max(peak,net)
            self.assertEqual(b.accrued,max(Decimal(0),peak)*Decimal('.10'))
            self.assertEqual(b.settle(str(i),str(value)),0)
