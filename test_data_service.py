import json
import os
import unittest
from urllib.request import urlopen
from data_service import CATALOG, provider_status


class DataServiceTests(unittest.TestCase):
    def test_demo_status_is_explicit(self):
        os.environ.pop("MARKET_DATA_BASE_URL", None)
        os.environ.pop("MARKET_DATA_API_KEY", None)
        self.assertEqual(provider_status()["mode"], "demo")
        self.assertFalse(provider_status()["realTime"])

    def test_catalog_has_bist_us_and_etf(self):
        self.assertTrue(any(x["exchange"] == "BIST" for x in CATALOG))
        self.assertTrue(any(x["exchange"] == "NASDAQ" for x in CATALOG))
        self.assertTrue(any(x["assetType"] == "ETF" for x in CATALOG))


if __name__ == "__main__":
    unittest.main()
