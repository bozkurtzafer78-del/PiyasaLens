import tempfile
import unittest
from pathlib import Path

from twelve_data_batch import DEFAULT_US_UNIVERSE, _read_universe


class TwelveDataBatchTests(unittest.TestCase):
    def test_missing_universe_uses_safe_us_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = _read_universe(Path(directory) / "missing-universe.json")
        self.assertEqual(payload["US"][:3], ["AAPL", "MSFT", "NVDA"])
        self.assertEqual(len(payload["US"]), len(DEFAULT_US_UNIVERSE))


if __name__ == "__main__":
    unittest.main()
