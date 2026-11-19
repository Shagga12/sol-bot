import json
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal as D
from test_live import config, Fake, fill, NOW, RULES
from capital_connect_v1.live import Halt, floor
from capital_connect_v1.protected import ProtectedJournal, ProtectedWorker

class BracketExchange(Fake):
    def __init__(self):
        super().__init__();self.child=None;self.buy_fills=[];self.child_fills=[]
    def request(self,endpoint,params=None,write=False):
        if write:
            self.writes.append(params)
            if self.fail_write:raise Halt('uncertain submission')
            q=D(params['qty']);v=q*D(params['price'])
            self.order={'orderId':'entry-id','orderLinkId':params['orderLinkId'],'symbol':'BTCUSDT','side':'Buy',
                        'orderStatus':'Filled','cumExecQty':str(q),'cumExecValue':str(v)}
            f=fill('Buy',str(q),str(v),str(q*D('.001')),'BTC');f['orderId']='entry-id';self.buy_fills=[f]
            child_q=floor(q*(1-D('.001')),RULES['lotSizeFilter']['basePrecision'])
            self.child={'orderId':'exit-id','orderLinkId':'','symbol':'BTCUSDT','side':'Sell','orderStatus':'Untriggered',
                        'qty':str(child_q),'takeProfit':params['takeProfit'],'stopLoss':params['stopLoss'],
                        'cumExecQty':'0','cumExecValue':'0'}
            return {'orderId':'entry-id'}
        if endpoint.endswith('/realtime') and 'limit' in params:
            return {'list':[self.child] if self.child and self.child['orderStatus']=='Untriggered' else []}
        if endpoint.endswith('/realtime') or endpoint.endswith('/history'):
            return {'list':[self.child if params.get('orderId')=='exit-id' else self.order]}
        if endpoint.endswith('/list'):
            return {'list':self.child_fills if params.get('orderId')=='exit-id' else self.buy_fills}
        return super().request(endpoint,params,write)
    def execute_exit(self):
        q=D(self.child['qty']);v=q*D('65000')
        self.child.update(orderStatus='Filled',cumExecQty=str(q),cumExecValue=str(v))
        f=fill('Sell',str(q),str(v),str(v*D('.001')),'USDT');f['orderId']='exit-id';self.child_fills=[f]

class ProtectedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'journal')
        self.c=config();self.api=BracketExchange();self.j=ProtectedJournal(self.path,self.c,'owner')
        self.worker=ProtectedWorker(self.c,self.api,self.j)
    def tearDown(self):self.j.db.close();self.tmp.cleanup()
    def enter(self):
        p=self.worker.payload('Buy',D('10'),RULES,self.api.bid,self.api.ask,D('.001'),NOW)
        self.worker.submit(p,NOW)
    def test_protection_is_in_original_entry_and_recovered_without_resubmission(self):
        self.enter();self.assertIn('stopLoss',self.api.writes[0])
        self.assertFalse(self.worker.reconcile(NOW+1))
        self.assertEqual(len(self.j.pending()),1)
        self.j.db.close();self.j=ProtectedJournal(self.path,self.c,'owner')
        self.worker=ProtectedWorker(self.c,self.api,self.j)
        self.assertFalse(self.worker.reconcile(NOW+2))
        self.assertEqual(len(self.api.writes),1)
        self.api.execute_exit()
        self.assertTrue(self.worker.reconcile(NOW+3))
        self.assertEqual(self.j.pending(),[])
        self.assertEqual(self.j.db.execute('SELECT state FROM live_protection').fetchone()[0],'COMPLETED')
        self.assertLess(self.j.position()[0]*self.api.bid,D('1'))
    def test_protection_discovered_in_tpsl_order_filter(self):
        self.enter()
        original=self.api.request
        filters=[]
        def filtered(endpoint,params=None,write=False):
            if endpoint.endswith('/realtime') and params and 'limit' in params:
                filters.append(params.get('orderFilter'))
                if params.get('orderFilter')!='tpslOrder':
                    return {'list':[]}
            return original(endpoint,params,write)
        self.api.request=filtered
        self.assertFalse(self.worker.reconcile(NOW+1))
        self.assertEqual(self.j.db.execute('SELECT state FROM live_protection').fetchone()[0],'ACTIVE')
        self.assertIn('tpslOrder',filters)
        self.assertEqual(len(self.api.writes),1)

    def test_missing_bracket_halts_instead_of_buying_again(self):
        self.enter();self.api.child=None
        with self.assertRaises(Halt):self.worker.reconcile(NOW+1)
        self.assertEqual(len(self.api.writes),1)
    def test_cancelled_protection_blocks_more_entries(self):
        self.enter();self.worker.reconcile(NOW+1)
        self.api.child['orderStatus']='Deactivated'
        with self.assertRaises(Halt):self.worker.reconcile(NOW+2)
        self.assertEqual(len(self.api.writes),1)
    def test_manual_sell_does_not_race_locked_exchange_bracket(self):
        with self.assertRaises(Halt):self.worker.submit({'side':'Sell'},NOW)
        self.assertEqual(self.api.writes,[])
    def test_uncertain_entry_is_journalled_before_write(self):
        self.api.fail_write=True
        with self.assertRaises(Halt):self.enter()
        self.assertEqual(len(self.j.pending()),1)
        self.assertEqual(self.j.db.execute('SELECT state FROM live_protection').fetchone()[0],'ENTRY_INTENT')
