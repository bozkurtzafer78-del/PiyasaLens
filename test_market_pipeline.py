import unittest

from market_batch import normalize_row, score_candidate


class MarketPipelineTests(unittest.TestCase):
    def test_normalizes_scanner_row(self):
        row = {"s": "BIST:THYAO", "d": ["Türk Hava Yolları", 312.4, 1.2, 1000, 900, 100000, 5, 1, 1.2, 2, 15, 8, 10, 20, 5, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, "buy"]}
        item = normalize_row(row, "BIST")
        self.assertEqual(item["symbol"], "THYAO")
        self.assertEqual(item["market"], "BIST")
        self.assertEqual(item["price"], 312.4)

    def test_score_is_explainable_and_bounded(self):
        item = score_candidate({"pe": 8, "roe": 20, "revenue_growth": 15, "rsi_14": 55, "debt_to_equity": 40})
        self.assertGreaterEqual(item["screen_score"], 0)
        self.assertLessEqual(item["screen_score"], 100)
        self.assertTrue(item["screen_reasons"])


if __name__ == "__main__":
    unittest.main()
