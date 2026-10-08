import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from backend.enrichment import enrich
from backend.normalized_schema import Instrument, Quote, AnalysisSnapshot
from backend.divergence_engine import analyze
from market_batch import score_candidate
from twelve_data_batch import collect_all, collect_market, TwelveDataError
from gemini_analysis import analyze_candidates


class RegressionTests(unittest.TestCase):
    def test_single_metric_cannot_produce_high_score(self):
        self.assertIsNone(score_candidate({'pe': 5})['screen_score'])

    def test_missing_weight_does_not_inflate_score(self):
        result = score_candidate({'pe': 5, 'roe': 50, 'revenue_growth': 50})
        self.assertLessEqual(result['screen_score'], 70)
        self.assertEqual(result['score_coverage'], .7)

    @patch.dict(os.environ, {}, clear=True)
    @patch('bist_data_service.collect_bist', return_value={'items': [{'symbol': 'TEST'}]})
    def test_bist_does_not_require_us_key(self, collect):
        output = collect_all(markets=['BIST'])
        self.assertIn('BIST', output['markets'])
        collect.assert_called_once()

    @patch('twelve_data_batch._request', return_value={'AAPL': {'status': 'error'}})
    def test_all_symbols_failed_is_error(self, request):
        with self.assertRaises(TwelveDataError):
            collect_market('US', ['AAPL'], 'https://example.test', 'fake', 1)

    @patch('twelve_data_batch._request', return_value={'close': '100', 'datetime': '2026-10-08'})
    def test_single_symbol_unwrapped_response(self, request):
        result = collect_market('US', ['AAPL'], 'https://example.test', 'fake', 1)
        self.assertEqual(result['items'][0]['price'], 100)

    @patch('twelve_data_batch._request', return_value={'AAPL': {'close': '100', 'datetime': '2026-10-08'}, 'MSFT': {'status': 'error'}})
    def test_partial_errors_preserved(self, request):
        result = collect_market('US', ['AAPL', 'MSFT'], 'https://example.test', 'fake', 2)
        self.assertEqual(result['row_count'], 1)
        self.assertIn('MSFT', result['errors'][0])

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'fake'}, clear=True)
    @patch('gemini_analysis.urlopen')
    def test_no_ai_request_without_research_ready_data(self, request):
        self.assertEqual(analyze_candidates({'BIST': [{'symbol': 'TEST', 'screen_score': None}]})['status'], 'skipped')
        request.assert_not_called()

    def test_sourced_fundamentals_and_expiry(self):
        item = {'market': 'BIST', 'symbol': 'TEST'}
        date = datetime.now(timezone.utc).isoformat()
        record = {'source': 'https://example.test/report', 'as_of': date, 'pe': 8, 'roe': 20}
        result = enrich(dict(item), {'BIST:TEST': record})
        self.assertEqual(result['pe'], 8)
        record['as_of'] = (datetime.now(timezone.utc) - timedelta(days=181)).isoformat()
        self.assertNotIn('pe', enrich(dict(item), {'BIST:TEST': record}))

    def test_quote_only_is_insufficient(self):
        snapshot = AnalysisSnapshot(Instrument('TEST', 'Test', 'BIST', 'XIST', 'Hisse', 'TRY'), Quote('TEST', 100, datetime.now(timezone.utc).isoformat(), 'delayed', 'test', 'TRY'))
        self.assertEqual(analyze(snapshot)['newBuy'], 'Veri yetersiz')

    @patch('collect_and_analyze.collect_all', return_value={'markets': {}, 'errors': ['provider failed']})
    @patch('sys.argv', ['collect_and_analyze.py'])
    def test_failed_refresh_preserves_previous_snapshot(self, collect):
        import collect_and_analyze
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'data').mkdir()
            path = root / 'data/latest_market.json'; path.write_text('previous')
            with patch.object(collect_and_analyze, 'APP_DIR', root):
                self.assertEqual(collect_and_analyze.main(), 1)
            self.assertEqual(path.read_text(), 'previous')

    def test_old_quote_does_not_become_fresh_on_collection(self):
        from backend.quality import fresh_quote
        self.assertFalse(fresh_quote({'as_of': (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()}))
        self.assertTrue(fresh_quote({'as_of': datetime.now(timezone.utc).isoformat()}))
        self.assertFalse(fresh_quote({'as_of': None}))

    def test_zero_daily_change_is_preserved(self):
        from bist_data_service import _normalize
        self.assertEqual(_normalize({'symbol': 'TEST', 'price': 100, 'change_percent': 0})['change_pct'], 0)

    def test_partial_refresh_retains_failed_market_source_time(self):
        from backend.snapshot import retain_missing_markets
        from pathlib import Path
        import json
        old = {'provider': 'test', 'markets': {'BIST': {'items': [{'symbol': 'TEST', 'as_of': '2026-01-01'}], 'fetched_at': '2026-01-01'}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'market.json'; path.write_text(json.dumps(old))
            output = retain_missing_markets({'provider': 'test', 'markets': {'US': {'items': [{'symbol': 'US'}]}}, 'errors': []}, path, ['BIST', 'US'])
        self.assertTrue(output['markets']['BIST']['retained'])
        self.assertEqual(output['markets']['BIST']['items'][0]['as_of'], '2026-01-01')
        self.assertTrue(output['errors'])

    def test_wrong_provider_snapshot_cannot_be_reused(self):
        from backend.snapshot import retain_missing_markets
        from pathlib import Path
        import json
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'market.json'; path.write_text(json.dumps({'provider': 'legacy', 'markets': {'BIST': {'items': [1]}}}))
            output = retain_missing_markets({'provider': 'current', 'markets': {}, 'errors': []}, path, ['BIST'])
        self.assertEqual(output['markets'], {})
