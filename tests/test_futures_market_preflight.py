import unittest
from capital_connect_v1.futures_market_preflight import inspect_market, FuturesPreflightError

class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, *args):
        import json
        return json.dumps(self.payload).encode()

class Opener:
    def __init__(self, payload):
        self.payload = payload
    def open(self, request, timeout):
        assert request.full_url.startswith("https://api-testnet.bybit.com/v5/market/instruments-info?")
        return Response(self.payload)

def payload(**changes):
    instrument = {
        "symbol": "SOLUSDT", "status": "Trading",
        "contractType": "LinearPerpetual", "settleCoin": "USDT",
        "lotSizeFilter": {"minOrderQty": "0.1", "qtyStep": "0.1"},
        "priceFilter": {"tickSize": "0.01"},
    }
    instrument.update(changes)
    return {"retCode": 0, "result": {"list": [instrument]}}

class FuturesMarketPreflightTests(unittest.TestCase):
    def test_valid_market_is_read_only(self):
        result = inspect_market(opener=Opener(payload()))
        self.assertTrue(result["market_trading"])
        self.assertFalse(result["orders_enabled"])
        self.assertFalse(result["exchange_protection_verified"])

    def test_reject_spot_contract(self):
        with self.assertRaises(FuturesPreflightError):
            inspect_market(opener=Opener(payload(contractType="Spot")))

    def test_reject_invalid_min_quantity(self):
        with self.assertRaises(FuturesPreflightError):
            inspect_market(opener=Opener(payload(lotSizeFilter={"minOrderQty": "0", "qtyStep": "0.1"})))

    def test_reject_closed_market(self):
        with self.assertRaises(FuturesPreflightError):
            inspect_market(opener=Opener(payload(status="Closed")))

    def test_reject_unknown_environment(self):
        with self.assertRaises(FuturesPreflightError):
            inspect_market("invalid", opener=Opener(payload()))

if __name__ == "__main__":
    unittest.main()
