import unittest,json,time
from unittest.mock import patch,MagicMock
import market_chart as market
from activation_control import ActivationControl

class MarketTests(unittest.TestCase):
    def test_public_prices_sorted_and_cached(self):
        now=time.time();payload={'retCode':0,'result':{'category':'spot','symbol':'BTCUSDT','list':[[str(int((now-10)*1000)),'0','0','0','65001'],[str(int((now-310)*1000)),'0','0','0','65000']]}}
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps(payload).encode()
        opener=MagicMock();opener.open.return_value=response
        with patch.object(market,'_cache',None),patch.object(market,'build_opener',return_value=opener):
            result=market.market_chart();self.assertEqual(result['points'][0]['price'],'65000')
            self.assertEqual(market.market_chart(),result);opener.open.assert_called_once()
            self.assertNotIn('X-BAPI-API-KEY',dict(opener.open.call_args.args[0].header_items()))
    def test_wrong_symbol_is_rejected(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"retCode":0,"result":{"symbol":"ETHUSDT","category":"spot"}}'
        opener=MagicMock();opener.open.return_value=response
        with patch.object(market,'_cache',None),patch.object(market,'build_opener',return_value=opener):
            with self.assertRaises(ValueError):market.market_chart()
    def test_chart_secret_fields_and_nonfinite_are_rejected(self):
        report={'state':'STOPPED','orders_enabled':False,'worker_id':'a'*64,'config_digest':'b'*64,'environment':'mainnet','ready':True}
        control=ActivationControl(lambda:1000)
        chart={'fills':[{'ts':100,'side':'Buy','price':'1','qty':'1','pnl':'NaN'}],'levels':[],'total_fills':1}
        with self.assertRaises(ValueError):control.update({**report,'chart':chart})
        with self.assertRaises(ValueError):control.update({**report,'chart':{'apiSecret':'x'}})
