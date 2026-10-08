"""Düşük frekanslı, önbellekli toplu piyasa verisi adaptörü.

TradingView erişimi için yalnızca izin verilen bir endpoint kullanılmalıdır.
Bu modül proxy rotasyonu, CAPTCHA aşma veya gizli istemci davranışı içermez.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from network_tls import verified_context


DEFAULT_COLUMNS = [
    "name", "close", "change", "volume", "average_volume_10d_calc",
    "market_cap_basic", "price_earnings_ttm", "price_sales_current",
    "price_book_fq", "dividend_yield_recent", "return_on_equity",
    "return_on_assets", "net_income", "total_revenue", "total_debt",
    "total_equity", "debt_to_equity", "gross_margin", "operating_margin",
    "net_margin", "earnings_per_share_diluted_ttm",
    "earnings_per_share_diluted_yoy_growth_percent",
    "total_revenue_yoy_growth_percent", "relative_volume_10d_calc",
    "RSI", "MACD.macd", "Recommend.All",
]


class MarketDataError(RuntimeError):
    pass


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_row(row: dict, market: str, columns: list[str] = DEFAULT_COLUMNS) -> dict:
    values = row.get("d", row.get("data", []))
    raw = dict(zip(columns, values)) if isinstance(values, list) else values
    source_symbol = str(row.get("s", row.get("symbol", "")))
    symbol = source_symbol.split(":", 1)[-1].upper()
    return {
        "symbol": symbol,
        "source_symbol": source_symbol,
        "market": market,
        "name": raw.get("name") or symbol,
        "price": _number(raw.get("close")),
        "change_pct": _number(raw.get("change")),
        "volume": _number(raw.get("volume")),
        "average_volume": _number(raw.get("average_volume_10d_calc")),
        "market_cap": _number(raw.get("market_cap_basic")),
        "pe": _number(raw.get("price_earnings_ttm")),
        "price_sales": _number(raw.get("price_sales_current")),
        "price_book": _number(raw.get("price_book_fq")),
        "dividend_yield": _number(raw.get("dividend_yield_recent")),
        "roe": _number(raw.get("return_on_equity")),
        "roa": _number(raw.get("return_on_assets")),
        "net_income": _number(raw.get("net_income")),
        "revenue": _number(raw.get("total_revenue")),
        "total_debt": _number(raw.get("total_debt")),
        "total_equity": _number(raw.get("total_equity")),
        "debt_to_equity": _number(raw.get("debt_to_equity")),
        "gross_margin": _number(raw.get("gross_margin")),
        "operating_margin": _number(raw.get("operating_margin")),
        "net_margin": _number(raw.get("net_margin")),
        "eps": _number(raw.get("earnings_per_share_diluted_ttm")),
        "eps_growth": _number(raw.get("earnings_per_share_diluted_yoy_growth_percent")),
        "revenue_growth": _number(raw.get("total_revenue_yoy_growth_percent")),
        "relative_volume": _number(raw.get("relative_volume_10d_calc")),
        "rsi_14": _number(raw.get("RSI")),
        "macd": _number(raw.get("MACD.macd")),
        "recommendation": raw.get("Recommend.All"),
    }


def _bounded_score(value, low, high):
    if value is None:
        return None
    return max(0.0, min(100.0, (value - low) / (high - low) * 100))


def score_candidate(item: dict) -> dict:
    """Gemini öncesi açıklanabilir ve deterministik aday puanı."""
    components = []
    if item.get("pe") is not None and item["pe"] > 0:
        components.append(("değerleme", 100 - min(item["pe"], 50) * 1.5, .30))
    if item.get("roe") is not None:
        components.append(("kârlılık", max(0, min(100, item["roe"] * 2)), .20))
    if item.get("revenue_growth") is not None:
        components.append(("büyüme", max(0, min(100, 50 + item["revenue_growth"])), .20))
    if item.get("rsi_14") is not None:
        components.append(("teknik", 100 - abs(item["rsi_14"] - 55) * 1.5, .15))
    if item.get("debt_to_equity") is not None:
        components.append(("borçluluk", 100 - min(max(item["debt_to_equity"], 0), 300) / 3, .15))
    total_weight = sum(weight for _, _, weight in components)
    score = round(sum(value * weight for _, value, weight in components) / total_weight) if total_weight else None
    item["screen_score"] = score
    item["screen_reasons"] = [name for name, _, _ in sorted(components, key=lambda part: part[1], reverse=True)[:3]]
    return item


class BatchCollector:
    def __init__(self, cache_dir="data/cache", min_interval_seconds=3, max_rows=5000, timeout=30):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self.max_rows = int(max_rows)
        self.timeout = int(timeout)
        self.throttle_file = self.cache_dir / ".last_request"

    def _cache_path(self, market):
        return self.cache_dir / f"{market.lower()}_scan.json"

    def _read_cache(self, market, ttl_seconds, force=False):
        path = self._cache_path(market)
        if force or not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched = payload.get("fetched_at_epoch", 0)
        return payload if time.time() - fetched <= ttl_seconds else None

    def _throttle(self):
        if self.throttle_file.exists():
            elapsed = time.time() - float(self.throttle_file.read_text(encoding="utf-8"))
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
        self.throttle_file.write_text(str(time.time()), encoding="utf-8")

    def collect(self, market, endpoint, ttl_seconds=86400, force=False):
        cached = self._read_cache(market, ttl_seconds, force)
        if cached:
            cached["cache"] = "hit"
            return cached
        if not endpoint:
            raise MarketDataError(f"{market} için izinli veri endpoint'i yapılandırılmadı.")
        columns = DEFAULT_COLUMNS
        body = {"columns": columns, "options": {"lang": "en"}, "range": [0, self.max_rows], "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}}
        self._throttle()
        request = Request(endpoint, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "PiyasaLens/1.0"}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout, context=verified_context()) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise MarketDataError(f"{market} toplu veri isteği başarısız: {exc}") from exc
        if raw.get("error"):
            raise MarketDataError(f"{market} sağlayıcı hatası: {raw['error']}")
        items = [score_candidate(normalize_row(row, market, columns)) for row in raw.get("data", [])]
        payload = {"market": market, "source": endpoint, "fetched_at": datetime.now(timezone.utc).isoformat(), "fetched_at_epoch": time.time(), "row_count": len(items), "items": items, "cache": "miss"}
        self._cache_path(market).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
