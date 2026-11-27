import unittest
from unittest.mock import patch
import cc_binance_demo_v2 as m
class DemoTests(unittest.TestCase):
 def setUp(self):
  m.S.pop('next_entry_at',None)
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
 def test_entry_cooldown(self):
  m.S['running']=True
  with patch.object(m.time,'monotonic',return_value=1000) as clock:
   for p in range(100,120):m.tick(p)
   self.assertIsNotNone(m.S['position'])
   self.assertEqual(m.S['next_entry_at'],1900)
   m.tick(110)
   self.assertIsNone(m.S['position'])
   clock.return_value=1899
   m.S['history']=list(range(100,120))
   m.tick(120)
   self.assertIsNone(m.S['position'])
   clock.return_value=1900
   m.tick(121)
   self.assertIsNotNone(m.S['position'])
if __name__=='__main__':unittest.main()
