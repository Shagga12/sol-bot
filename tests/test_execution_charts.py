import unittest,json,tempfile
from pathlib import Path
from dataclasses import asdict
from capital_connect_v1.execution_charts import chart_snapshot
from capital_connect_v1.protected import ProtectedJournal
from test_live import config

class ExecutionChartTests(unittest.TestCase):
    def test_actual_fills_cumulative_pnl_and_no_fill_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            c=config();j=ProtectedJournal(str(Path(directory)/'execution-journal.sqlite3'),c,'owner')
            for key,side,qty,value,pnl,ts in [('buy','Buy','.001','60','0',100),('sell','Sell','.001','61','.8',200),('cancel','Buy','0','0','0',300)]:
                result=json.dumps({'executed_qty':qty,'executed_value':value})
                j.db.execute('INSERT INTO live_orders(link,created,side,payload,terminal,result,pnl,settled) VALUES(?,?,?, ?,1,?,?,?)',(key,ts,side,'{}',result,pnl,ts))
            before=j.db.total_changes
            result=chart_snapshot(directory,c)
            self.assertEqual(result['total_fills'],2)
            self.assertEqual(result['fills'][-1]['pnl'],'0.8')
            self.assertEqual(result['fills'][-1]['price'],'6.1E+4')
            self.assertEqual(j.db.total_changes,before)
            self.assertIsNone(chart_snapshot(directory,config(order_usdt='9')))
            j.db.close()
    def test_missing_journal_is_unknown_not_fake_zero(self):
        with tempfile.TemporaryDirectory() as directory:self.assertIsNone(chart_snapshot(directory,config()))
