import unittest
from activation_control import ActivationControl

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.now=100
        self.control=ActivationControl(lambda:self.now)
        self.report={'state':'STOPPED','orders_enabled':False,'worker_id':'a'*64,'config_digest':'b'*64,'environment':'testnet','ready':True}
    def test_start_requires_fresh_validated_worker(self):
        with self.assertRaises(ValueError): self.control.command('START')
        self.control.update({**self.report,'ready':False})
        with self.assertRaises(ValueError): self.control.command('START')
        self.control.update(self.report)
        self.now+=21
        with self.assertRaises(ValueError): self.control.command('START')
    def test_command_is_bound_to_session_and_acknowledged_separately(self):
        self.control.update(self.report)
        self.control.command('START')
        self.assertFalse(self.control.status()['orders_running'])
        command=self.control.update(self.report)
        self.assertEqual(command['action'],'START')
        running={**self.report,'state':'RUNNING','orders_enabled':True}
        self.control.update(running)
        self.assertTrue(self.control.status()['orders_running'])
        self.assertFalse(self.control.status()['real_trading_active'])
        self.control.command('STOP')
        self.assertTrue(self.control.status()['orders_running'])
        self.control.update(self.report)
        self.assertFalse(self.control.status()['orders_running'])
    def test_restart_cannot_resume_old_start(self):
        self.control.update(self.report);self.control.command('START')
        new={**self.report,'worker_id':'c'*64}
        self.assertEqual(self.control.update(new)['action'],'STOP')
    def test_invalid_report_does_not_unlock_start(self):
        for bad in ({**self.report,'ready':'true'},{**self.report,'state':'STOPPED','orders_enabled':True},{**self.report,'config_digest':'invalid'}):
            with self.assertRaises(ValueError):self.control.update(bad)
        self.assertFalse(self.control.status()['can_activate'])
