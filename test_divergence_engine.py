import unittest

from backend.divergence_engine import analyze, calculate_divergence
from backend.normalized_schema import AnalysisSnapshot, Evidence, Instrument, Quote
from data_service import build_analysis


class DivergenceEngineTests(unittest.TestCase):
    def test_insufficient_data_returns_explicit_status(self):
        res = calculate_divergence(price=None, target=100)
        self.assertEqual(res["new_buy"], "Veri yetersiz")
        self.assertEqual(res["holding"], "Veri yetersiz")

    def test_four_ninety_nine_blocked(self):
        # Target with net potential under 5% should not recommend "Al"
        res = calculate_divergence(price=100, target=105, buy_low=90, buy_high=105, buy_cost=0.2, sell_cost=0.2)
        self.assertNotEqual(res["new_buy"], "Al")
        self.assertLess(res["net"], 5.0)

    def test_band_missed_produces_wait(self):
        res = calculate_divergence(price=110, target=130, buy_low=90, buy_high=105)
        self.assertTrue(res["band_missed"])
        self.assertEqual(res["new_buy"], "Bekle / İzle")

    def test_qualifying_setup_produces_buy(self):
        res = calculate_divergence(price=100, target=120, buy_low=95, buy_high=105, stop=95, min_ratio=2.0)
        self.assertEqual(res["new_buy"], "Al")
        self.assertEqual(res["holding"], "Tut")

    def test_broken_thesis_changes_holding_decision(self):
        res = calculate_divergence(price=100, target=115, thesis="broken")
        self.assertEqual(res["holding"], "Azalt / Sat")

    def test_unified_schema_to_dict_integrity(self):
        inst = Instrument(symbol="THYAO", name="Türk Hava Yolları", market="BIST", exchange="XIST", asset_type="Hisse")
        quote = Quote(symbol="THYAO", price=312.4, status="demo", source="katalog")
        ev = Evidence(source="KAP", title="Mali Tablo")
        snapshot = AnalysisSnapshot(instrument=inst, quote=quote, evidence=[ev], data_quality="demo")
        d = snapshot.to_dict()
        self.assertEqual(d["instrument"]["symbol"], "THYAO")
        self.assertEqual(d["quote"]["price"], 312.4)
        self.assertEqual(len(d["evidence"]), 1)
        self.assertEqual(d["data_quality"], "demo")

    def test_build_analysis_for_catalog_instrument(self):
        res = build_analysis("THYAO")
        self.assertIsNotNone(res)
        self.assertIn("snapshot", res)
        self.assertIn("analysis", res)
        self.assertEqual(res["snapshot"]["instrument"]["symbol"], "THYAO")


if __name__ == "__main__":
    unittest.main()
