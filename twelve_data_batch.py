"""Twelve Data EOD toplu veri adaptörü.

Bir batch HTTP çağrısı kullanılmasına rağmen Twelve Data krediyi sembol başına
hesaplar. Bu nedenle varsayılan evren, ücretsiz 800/gün kotasının altında
tutulur ve sembol sayısı açık bir ayarla sınırlandırılır.
"""
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from market_batch import load_env_file, score_candidate
from network_tls import verified_context


class TwelveDataError(RuntimeError):
    pass


DEFAULT_US_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "BRK.B", "LLY", "JPM", "V", "UNH", "XOM", "MA", "COST", "HD", "PG",
    "JNJ", "ABBV", "NFLX", "CRM", "ORCL", "WMT", "BAC", "KO", "MRK", "PEP",
    "AMD", "ADBE", "TMO", "CSCO", "MCD", "ACN", "LIN", "ABT", "IBM", "GE",
    "QCOM", "INTU", "CAT", "TXN", "AMAT", "DHR", "VZ", "ISRG", "NOW", "PFE",
    "DIS", "UBER", "SPOT", "PYPL", "PLTR", "SHOP", "SNOW", "PANW", "CRWD", "COIN",
]


def _number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _read_universe(path):
    universe_file = Path(path)
    if not universe_file.exists():
        return {"US": DEFAULT_US_UNIVERSE}
    payload = json.loads(universe_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TwelveDataError("Twelve Data evren dosyası nesne olmalı.")
    return {market: [str(symbol).upper() for symbol in symbols] for market, symbols in payload.items()}


def _request(endpoint, symbols, api_key):
    params = urlencode({"symbol": ",".join(symbols), "apikey": api_key, "outputsize": 1})
    request = Request(f"{endpoint}?{params}", headers={"Accept": "application/json", "User-Agent": "PiyasaLens/1.0"})
    try:
        with urlopen(request, timeout=30, context=verified_context()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise TwelveDataError(f"Twelve Data bağlantısı başarısız: {exc}") from exc
    if not isinstance(payload, dict):
        raise TwelveDataError("Twelve Data yanıtı JSON nesnesi olmalı.")
    if payload.get("status") == "error":
        raise TwelveDataError(payload.get("message", "Twelve Data sağlayıcı hatası."))
    return payload


def _normalize(item, requested_symbol, market):
    row = item if isinstance(item, dict) else {}
    symbol = str(row.get("symbol") or requested_symbol).split(":")[-1].upper()
    return score_candidate({
        "symbol": symbol, "source_symbol": row.get("symbol") or requested_symbol, "market": market,
        "name": symbol, "price": _number(row.get("close") or row.get("price")),
        "change_pct": None, "volume": None, "average_volume": None, "market_cap": None,
        "pe": None, "price_sales": None, "price_book": None, "dividend_yield": None,
        "roe": None, "roa": None, "net_income": None, "revenue": None, "total_debt": None,
        "total_equity": None, "debt_to_equity": None, "gross_margin": None, "operating_margin": None,
        "net_margin": None, "eps": None, "eps_growth": None, "revenue_growth": None,
        "relative_volume": None, "rsi_14": None, "macd": None, "recommendation": None,
        "currency": row.get("currency"), "as_of": row.get("datetime"), "source": "Twelve Data EOD",
    })


def collect_market(market, symbols, endpoint, api_key, max_symbols):
    selected = symbols[:max_symbols]
    if not selected:
        return {"market": market, "source": endpoint, "fetched_at": datetime.now(timezone.utc).isoformat(), "row_count": 0, "items": [], "cache": "miss"}
    requested = selected
    items = []
    errors = []
    chunk_size = max(1, int(os.getenv("TWELVE_DATA_SYMBOLS_PER_REQUEST", "8")))
    for offset in range(0, len(requested), chunk_size):
        chunk = requested[offset:offset + chunk_size]
        payload = _request(endpoint, chunk, api_key)
        for requested_symbol in chunk:
            raw = payload.get(requested_symbol) or payload.get(requested_symbol.split(":")[-1])
            if raw is None and len(chunk) == 1 and ("close" in payload or "price" in payload):
                raw = payload
            if not isinstance(raw, dict) or raw.get("status") == "error":
                errors.append(f"{requested_symbol}: sağlayıcı yanıtı eksik/hatalı.")
                continue
            item = _normalize(raw, requested_symbol, market)
            if item["price"] is None or item["price"] <= 0 or not item["as_of"]:
                errors.append(f"{requested_symbol}: fiyat veya veri zamanı eksik.")
                continue
            items.append(item)
        if offset + chunk_size < len(requested):
            time.sleep(float(os.getenv("TWELVE_DATA_REQUEST_PAUSE_SECONDS", "60")))
    if not items:
        raise TwelveDataError(f"{market}: geçerli sembol verisi alınamadı.")
    return {"errors": errors, "market": market, "source": "Twelve Data · günlük kapanış", "provider": "Twelve Data EOD", "data_quality": "eod", "delayed": True, "fetched_at": datetime.now(timezone.utc).isoformat(), "row_count": len(items), "items": items, "cache": "miss", "requested_count": len(requested)}


def collect_all(universe_path="data/universe.json", markets=None):
    load_env_file()
    api_key = os.getenv("MARKET_DATA_API_KEY", "").strip()
    endpoint = os.getenv("MARKET_DATA_BASE_URL", "https://api.twelvedata.com/eod")
    max_symbols = int(os.getenv("TWELVE_DATA_MAX_SYMBOLS", "120"))
    market_limits = {"US": int(os.getenv("TWELVE_DATA_US_SYMBOLS", str(max_symbols)))}
    universe = _read_universe(universe_path)
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "provider": "BIST Data Service + Twelve Data EOD", "markets": {}, "errors": []}
    selected_markets = tuple(markets or ("BIST", "US"))
    for market in selected_markets:
        if market == "BIST":
            from bist_data_service import BistDataServiceError, collect_bist
            try:
                output["markets"][market] = collect_bist()
            except BistDataServiceError as exc:
                output["errors"].append(f"BIST: {exc}")
            continue
        if not api_key or api_key.lower() in {"replace-with-twelve-data-key", "your-api-key"}:
            output["errors"].append(f"{market}: MARKET_DATA_API_KEY yapılandırılmadı.")
            continue
        symbols = universe.get(market, [])[:market_limits.get(market, 0)]
        try:
            batch = collect_market(market, symbols, endpoint, api_key, len(symbols))
            if not batch["items"]:
                raise TwelveDataError("Evren boş veya geçerli veri yok.")
            output["markets"][market] = batch
            output["errors"].extend(batch.get("errors", []))
        except TwelveDataError as exc:
            output["errors"].append(f"{market}: {exc}")
    return output
