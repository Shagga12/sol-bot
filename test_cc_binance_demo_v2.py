import unittest
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import cc_binance_demo_v2 as m
class DemoTests(unittest.TestCase):
 def setUp(self):
  m.S.update(running=False,symbol='SOLUSDT',leverage=3,price=None,position=None,balance=1000.,trades=[],error='',history=[],pnl=0.)
 def position(self,d=1):
  m.S['position']=dict(entry=100.,direction=d,notional=30.,peak=0.)
 def test_stop(self):
  self.position();m.tick(98.9);self.assertIsNone(m.S['position']);self.assertLess(m.S['balance'],1000)
 def test_profit(self):
  self.position();m.tick(104.1);self.assertIsNone(m.S['position']);self.assertGreater(m.S['balance'],1000)
 def test_short(self):
  self.position(-1);m.tick(95.9);self.assertGreater(m.S['balance'],1000)
 def test_trailing(self):
  self.position();m.tick(102);m.tick(101.4);self.assertIsNone(m.S['position'])
 def test_stopped(self):
  for p in range(100,130):m.tick(p)
  self.assertIsNone(m.S['position'])
 def test_entry(self):
  m.S['running']=True
  for p in range(100,120):m.tick(p)
  self.assertIsNotNone(m.S['position'])

 def test_restart_recovers_trade_history_and_open_position(self):
  with TemporaryDirectory() as directory:
   path = Path(directory) / 'paper.sqlite3'
   with patch.object(m, 'STORE', m.StateStore(path)):
    self.position()
    m.update_state(lambda: m.apply_quote(104.1))
    self.position()
    m.update_state(lambda: m.S.update(running=True))
   snapshot = m.StateStore(path).load()
   self.assertEqual(snapshot, m.S)
   self.assertTrue(snapshot['running'])
   self.assertGreater(snapshot['balance'], 1000)
   self.assertEqual(len(snapshot['trades']), 1)
   self.assertIsNotNone(snapshot['position'])

 def test_failed_save_rolls_back_position_and_ledger(self):
  self.position()
  failing_store = Mock()
  failing_store.save.side_effect = sqlite3.OperationalError('disk unavailable')
  with patch.object(m, 'STORE', failing_store), self.assertRaises(sqlite3.OperationalError):
   m.update_state(lambda: m.apply_quote(104.1))
  self.assertIsNotNone(m.S['position'])
  self.assertEqual(m.S['balance'], 1000)
  self.assertFalse(m.S['trades'])
if __name__=='__main__':unittest.main()
