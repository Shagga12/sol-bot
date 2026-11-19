"""Spot worker whose entries carry exchange-held TP/SL, with durable ownership.
Stop preserves protective orders; never cancels them as part of stopping a process.
"""
import hashlib
import json
from .live import Journal, Worker, Halt, number, D
from .protection import attach_protection


def list_open_orders(api,symbol):
    # Bybit separates ordinary spot orders from exchange-held TP/SL and
    # conditional orders. A default realtime query does not cover all three.
    rows=[];ids=set()
    for order_filter in ('Order','tpslOrder','StopOrder'):
        cursor='';seen=set()
        while True:
            page=api.request('/v5/order/realtime',{'category':'spot','symbol':symbol,
                'orderFilter':order_filter,'limit':50,
                **({'cursor':cursor} if cursor else {})})
            for order in page.get('list',[]):
                identity=order.get('orderId')
                if not identity:raise Halt('Open order lacks exchange identity')
                if identity not in ids:
                    ids.add(identity);rows.append(order)
            cursor=page.get('nextPageCursor')
            if not cursor:break
            if cursor in seen or len(rows)>1000:
                raise Halt('Open-order pagination incomplete')
            seen.add(cursor)
    return rows


class ProtectedJournal(Journal):
    def __init__(self,path,config,uid):
        super().__init__(path,config,uid)
        self.db.execute('''CREATE TABLE IF NOT EXISTS live_protection(
            entry_link TEXT PRIMARY KEY, child_id TEXT UNIQUE, child_link TEXT,
            state TEXT NOT NULL, data TEXT NOT NULL)''')

    def reserve_protected(self,payload,now,bucket,before):
        with self.transaction():
            if self.pending():raise Halt('Pending order blocks new protected entry')
            if self.db.execute("SELECT 1 FROM live_protection WHERE state NOT IN ('COMPLETED','NO_FILL')").fetchone():
                raise Halt('Prior protection is not settled')
            if bucket is not None:self.db.execute('INSERT INTO live_scans VALUES(?)',(bucket,))
            self.db.execute('INSERT INTO live_orders(link,created,side,payload) VALUES(?,?,?,?)',
                            (payload['orderLinkId'],now,'Buy',json.dumps(payload)))
            data={'before':before,'takeProfit':payload['takeProfit'],'stopLoss':payload['stopLoss']}
            self.db.execute("INSERT INTO live_protection(entry_link,state,data) VALUES(?,'ENTRY_INTENT',?)",
                            (payload['orderLinkId'],json.dumps(data)))


class ProtectedWorker(Worker):
    def payload(self,side,amount,rules,bid,ask,fee,now):
        payload=super().payload(side,amount,rules,bid,ask,fee,now)
        return attach_protection(payload,self.c,rules,fee) if side=='Buy' else payload

    def submit(self,payload,now,bucket=None):
        if payload['side']!='Buy':
            raise Halt('Protected holdings exit through the exchange-held bracket only')
        if not all(payload.get(k) for k in ('takeProfit','stopLoss')):
            raise Halt('Unprotected entry refused')
        before=[r['orderId'] for r in list_open_orders(self.api,self.c.symbol)]
        self.journal.reserve_protected(payload,now,bucket,before)
        self.api.request('/v5/order/create',payload,write=True)
        return {'state':'ORDER_PENDING','side':'Buy','order_link_id':payload['orderLinkId'],
                'protection':'attached; awaiting exchange verification'}

    def reconcile(self,now):
        pending_cleared=super().reconcile(now)
        records=self.journal.db.execute("SELECT * FROM live_protection WHERE state NOT IN ('COMPLETED','NO_FILL')").fetchall()
        for record in records:
            entry=self.journal.db.execute('SELECT * FROM live_orders WHERE link=?',(record['entry_link'],)).fetchone()
            if not entry or not entry['terminal']:
                return False
            entry_result=json.loads(entry['result'])
            if number(entry_result['executed_qty'])==0:
                self.journal.db.execute("UPDATE live_protection SET state='NO_FILL' WHERE entry_link=?",(record['entry_link'],))
                continue
            if not record['child_id']:
                data=json.loads(record['data'])
                candidates=[r for r in list_open_orders(self.api,self.c.symbol) if
                    r.get('orderId') not in data['before'] and r.get('symbol')==self.c.symbol and r.get('side')=='Sell' and
                    r.get('takeProfit') and r.get('stopLoss') and
                    number(r['takeProfit'])==number(data['takeProfit']) and number(r['stopLoss'])==number(data['stopLoss'])]
                if len(candidates)!=1:
                    raise Halt('Attached protection could not be uniquely verified; inspect exchange holdings')
                child=candidates[0];qty,cost=self.journal.position()
                child_qty=number(child.get('qty'),True)
                if child_qty>qty:raise Halt('Protective exit exceeds bot-owned quantity')
                rules, bid, ask, fee = self.snapshot()
                uncovered=(qty-child_qty)*bid
                if uncovered>=number(rules['lotSizeFilter']['minOrderAmt'],True):
                    raise Halt('Tradable holdings are not fully covered by protection')
                link='cc-prot-'+hashlib.sha256(child['orderId'].encode()).hexdigest()[:26]
                payload={'qty':str(child_qty),'exchangeOrderId':child['orderId'],
                         'orderFilter':child.get('orderFilter') or 'tpslOrder'}
                with self.journal.transaction():
                    self.journal.db.execute("INSERT INTO live_orders(link,created,side,payload) VALUES(?,?,'Sell',?)",
                                            (link,now,json.dumps(payload)))
                    self.journal.db.execute("UPDATE live_protection SET child_id=?,child_link=?,state='ACTIVE' WHERE entry_link=?",
                                            (child['orderId'],link,record['entry_link']))
                return False
            child_row=self.journal.db.execute('SELECT * FROM live_orders WHERE link=?',(record['child_link'],)).fetchone()
            if not child_row or not child_row['terminal']:
                return False
            qty,cost=self.journal.position()
            rules,bid,ask,fee=self.snapshot()
            if qty*bid>=number(rules['lotSizeFilter']['minOrderAmt'],True):
                raise Halt('Protection ended with tradable holdings remaining; new entries blocked')
            self.journal.db.execute("UPDATE live_protection SET state='COMPLETED' WHERE entry_link=?",(record['entry_link'],))
        qty,cost=self.journal.position()
        if qty and not self.journal.pending():
            rules,bid,ask,fee=self.snapshot()
            if qty*bid>=number(rules['lotSizeFilter']['minOrderAmt'],True):
                raise Halt('Unprotected tradable holdings; inspect exchange before continuing')
        return pending_cleared and not self.journal.pending()
