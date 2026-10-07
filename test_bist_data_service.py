import unittest
from unittest.mock import patch

from bist_data_service import _normalize, collect_bist


class BistDataServiceTests(unittest.TestCase):
    def test_normalizes_delayed_quote(self):
        item = _normalize({
            "symbol": "THYAO",
            "name": "Türk Hava Yolları",
            "price": "312.40",
            "previous_close": "300.00",
            "volume": "1250000",
        })
        self.assertEqual(item["symbol"], "THYAO")
        self.assertEqual(item["market"], "BIST")
        self.assertEqual(item["price"], 312.4)
        self.assertAlmostEqual(item["change_pct"], 4.133333, places=4)
        self.assertTrue(item["delayed"])
        self.assertEqual(item["currency"], "TRY")

    @patch.dict("os.environ", {"BIST_DATA_SERVICE_URL": "https://bist.example.test", "BIST_DATA_SERVICE_API_KEY": "secret"}, clear=False)
    @patch("bist_data_service._request")
    def test_collects_all_quotes_without_twelve_data(self, request):
        request.return_value = {"last_update": "2026-10-07T16:15:00Z", "quotes": [{"symbol": "ASELS", "price": 100}]}
        result = collect_bist()
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["provider"], "BIST Data Service")
        self.assertTrue(result["delayed"])
        request.assert_called_once_with("https://bist.example.test", "secret")


if __name__ == "__main__":
    unittest.main()
