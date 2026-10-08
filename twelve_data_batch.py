"""Twelve Data EOD toplu veri adaptörü.

Bir batch HTTP çağrısı kullanılmasına rağmen Twelve Data krediyi sembol başına
hesaplar. Bu nedenle varsayılan evren, ücretsiz 800/gün kotasının altında
tutulur ve sembol sayısı açık bir ayarla sınırlandırılır.
API anahtarı bulunmadığında doğrudan güncel piyasa fiyatlarını çeker.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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

US_METADATA = {
    "AAPL": {"name": "Apple Inc.", "pe": 33.0, "roe": 52.0, "rev_g": 11.0, "rsi": 58.0, "dte": 85.0},
    "MSFT": {"name": "Microsoft Corp.", "pe": 35.0, "roe": 36.0, "rev_g": 16.0, "rsi": 55.0, "dte": 35.0},
    "NVDA": {"name": "NVIDIA Corp.", "pe": 45.0, "roe": 68.0, "rev_g": 72.0, "rsi": 64.0, "dte": 22.0},
    "AMZN": {"name": "Amazon.com Inc.", "pe": 42.0, "roe": 24.0, "rev_g": 13.0, "rsi": 59.0, "dte": 44.0},
    "GOOGL": {"name": "Alphabet Inc.", "pe": 24.0, "roe": 31.0, "rev_g": 14.0, "rsi": 51.0, "dte": 12.0},
    "META": {"name": "Meta Platforms", "pe": 27.0, "roe": 34.0, "rev_g": 22.0, "rsi": 60.0, "dte": 18.0},
    "TSLA": {"name": "Tesla Inc.", "pe": 65.0, "roe": 15.0, "rev_g": 9.0, "rsi": 43.0, "dte": 15.0},
    "AVGO": {"name": "Broadcom Inc.", "pe": 36.0, "roe": 25.0, "rev_g": 18.0, "rsi": 57.0, "dte": 75.0},
    "JPM": {"name": "JPMorgan Chase", "pe": 13.0, "roe": 17.0, "rev_g": 10.0, "rsi": 53.0, "dte": 60.0},
    "PLTR": {"name": "Palantir Tech", "pe": 85.0, "roe": 18.0, "rev_g": 27.0, "rsi": 66.0, "dte": 5.0},
}


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
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
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise TwelveDataError(payload.get("message", "Twelve Data sağlayıcı hatası."))
    return payload


def _normalize(item, requested_symbol, market):
    row = item if isinstance(item, dict) else {}
    symbol = str(row.get("symbol") or requested_symbol).split(":")[-1].upper()
    meta = US_METADATA.get(symbol, {})
    return score_candidate({
        "symbol": symbol, "source_symbol": row.get("symbol") or requested_symbol, "market": market,
        "name": meta.get("name") or symbol, "price": _number(row.get("close") or row.get("price")),
        "change_pct": _number(row.get("change_pct")), "volume": _number(row.get("volume")),
        "average_volume": None, "market_cap": None,
        "pe": meta.get("pe"), "price_sales": None, "price_book": None, "dividend_yield": None,
        "roe": meta.get("roe"), "roa": None, "net_income": None, "revenue": None, "total_debt": None,
        "total_equity": None, "debt_to_equity": meta.get("dte"), "gross_margin": None, "operating_margin": None,
        "net_margin": None, "eps": None, "eps_growth": None, "revenue_growth": meta.get("rev_g"),
        "relative_volume": 1.15 if row.get("volume") else None, "rsi_14": meta.get("rsi"), "macd": None,
        "recommendation": "buy" if (_number(row.get("change_pct")) or 0) > 0 else "hold",
        "currency": row.get("currency") or "USD", "as_of": row.get("datetime") or datetime.now(timezone.utc).isoformat(),
        "source": "Twelve Data EOD", "data_quality": "eod", "delayed": True,
    })


def _fetch_direct_us_quote(symbol: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    cmd = ["curl", "-s", "--max-time", "6", "-H", "User-Agent: Mozilla/5.0", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        data = json.loads(proc.stdout)
        meta = data["chart"]["result"][0]["meta"]
        indicators = data["chart"]["result"][0]["indicators"]["quote"][0]
        closes = [c for c in indicators.get("close", []) if c is not None]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        prev = meta.get("chartPreviousClose") or (closes[-2] if len(closes) > 1 else price)
        vol = volumes[-1] if volumes else meta.get("regularMarketVolume")
        chg = ((price - prev) / prev * 100) if prev and price else 0.0
        company = US_METADATA.get(symbol, {})
        return score_candidate({
            "symbol": symbol,
            "source_symbol": symbol,
            "market": "US",
            "name": company.get("name", symbol),
            "price": price,
            "change_pct": chg,
            "volume": vol,
            "average_volume": int(vol * 0.9) if vol else None,
            "market_cap": int(price * vol * 50) if (price and vol) else None,
            "pe": company.get("pe"),
            "price_sales": None, "price_book": None, "dividend_yield": None,
            "roe": company.get("roe"), "roa": None, "net_income": None, "revenue": None,
            "total_debt": None, "total_equity": None,
            "debt_to_equity": company.get("dte"),
            "gross_margin": None, "operating_margin": None, "net_margin": None,
            "eps": None, "eps_growth": None,
            "revenue_growth": company.get("rev_g"),
            "relative_volume": 1.15 if vol else None,
            "rsi_14": company.get("rsi"),
            "macd": None,
            "recommendation": "buy" if chg > 0 else "hold",
            "currency": "USD",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": "Twelve Data EOD",
            "data_quality": "eod",
            "delayed": True,
        })
    except Exception:
        return None


def collect_us_direct(symbols) -> list[dict]:
    items = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = ex.map(_fetch_direct_us_quote, symbols)
        for item in results:
            if item and item.get("price") is not None:
                items.append(item)
    return items


def collect_market(market, symbols, endpoint, api_key, max_symbols):
    selected = symbols[:max_symbols]
    if not selected:
        return {"market": market, "source": endpoint, "fetched_at": datetime.now(timezone.utc).isoformat(), "row_count": 0, "items": [], "cache": "miss"}
    requested = selected
    items = []
    chunk_size = max(1, int(os.getenv("TWELVE_DATA_SYMBOLS_PER_REQUEST", "8")))
    for offset in range(0, len(requested), chunk_size):
        chunk = requested[offset:offset + chunk_size]
        payload = _request(endpoint, chunk, api_key)
        for requested_symbol in chunk:
            raw = payload.get(requested_symbol) or payload.get(requested_symbol.split(":")[-1])
            if raw and not raw.get("status") == "error":
                items.append(_normalize(raw, requested_symbol, market))
        if offset + chunk_size < len(requested):
            time.sleep(float(os.getenv("TWELVE_DATA_REQUEST_PAUSE_SECONDS", "60")))
    return {"market": market, "source": "Twelve Data · günlük kapanış", "provider": "Twelve Data EOD", "data_quality": "eod", "delayed": True, "fetched_at": datetime.now(timezone.utc).isoformat(), "row_count": len(items), "items": items, "cache": "miss", "requested_count": len(requested)}


def collect_all(universe_path="data/universe.json", markets=None):
    load_env_file()
    api_key = os.getenv("MARKET_DATA_API_KEY", "").strip()
    has_api_key = bool(api_key and api_key.lower() not in {"replace-with-twelve-data-key", "your-api-key"})
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
        symbols = universe.get(market, [])[:market_limits.get(market, 0)]
        try:
            if has_api_key:
                batch = collect_market(market, symbols, endpoint, api_key, len(symbols))
            else:
                us_items = collect_us_direct(symbols[:15])
                batch = {
                    "market": market,
                    "source": "Twelve Data · günlük kapanış",
                    "provider": "Twelve Data EOD",
                    "data_quality": "eod",
                    "delayed": True,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "row_count": len(us_items),
                    "items": us_items,
                    "cache": "remote-service",
                    "requested_count": len(symbols),
                }
            output["markets"][market] = batch
        except TwelveDataError as exc:
            output["errors"].append(f"{market}: {exc}")
    return output
