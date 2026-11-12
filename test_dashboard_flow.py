"""Dashboard control-flow tests with a UI stub; not browser/rendering tests."""
import os
from pathlib import Path
import runpy
import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch


class Halt(Exception): pass


def ui(password='correct', submitted=True):
    s = types.ModuleType('streamlit')
    for name in ['set_page_config','title','warning','caption','metric','error','info','success','write','divider','subheader','json']:
        setattr(s, name, Mock())
    s.stop = Mock(side_effect=Halt)
    s.button = Mock(return_value=False)
    s.text_input = Mock(side_effect=lambda label, **kw: password if label == 'Dashboard password' else 'cc-1')
    s.form = Mock(return_value=nullcontext())
    s.selectbox = Mock(return_value='BTCUSDT')
    s.number_input = Mock(return_value=7)
    s.form_submit_button = Mock(return_value=submitted)
    return s


class DashboardFlowTest(unittest.TestCase):
    def run_app(self, s, env, receipt=None):
        with patch.dict(sys.modules, {'streamlit': s}), patch.dict(os.environ, env, clear=True), \
             patch('diagnostics.account_check', return_value={}) as account, \
             patch('order_reconciliation.reconcile', return_value=receipt) as lookup:
            try: runpy.run_path(str(Path(__file__).with_name('app.py')))
            except Halt: pass
        return account, lookup

    def test_missing_password_blocks_private_calls(self):
        account, lookup = self.run_app(ui(), {})
        account.assert_not_called()
        lookup.assert_not_called()

    def test_wrong_password_blocks_private_calls(self):
        account, lookup = self.run_app(ui(password='wrong'), {'BOT_DASHBOARD_PASSWORD': 'correct'})
        account.assert_not_called()
        lookup.assert_not_called()

    def test_authorized_lookup_checks_readonly_first_and_displays_receipt(self):
        s = ui()
        receipt = {'final': True, 'outcome': 'Filled'}
        account, lookup = self.run_app(s, {'BOT_DASHBOARD_PASSWORD': 'correct',
                                      'BYBIT_API_KEY': 'fixture-key', 'BYBIT_API_SECRET': 'fixture-secret'}, receipt)
        account.assert_called_once_with('fixture-key', 'fixture-secret')
        lookup.assert_called_once()
        s.json.assert_called_once_with(receipt)
        s.success.assert_called_once()
        self.assertTrue(any('nothing was saved' in str(c) for c in s.info.call_args_list))

    def test_unknown_never_shown_as_success(self):
        s = ui()
        self.run_app(s, {'BOT_DASHBOARD_PASSWORD': 'correct'}, {'final': False, 'outcome': 'UNKNOWN'})
        s.success.assert_not_called()
        self.assertTrue(any('unresolved' in str(c) for c in s.warning.call_args_list))

if __name__ == '__main__': unittest.main()
