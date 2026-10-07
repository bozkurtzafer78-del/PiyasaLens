"""Twelve Data EOD toplu veri adaptörü.

Bir batch HTTP çağrısı kullanılmasına rağmen Twelve Data krediyi sembol başına
hesaplar. Bu nedenle varsayılan evren, ücretsiz 800/gün kotasının altında
tutulur ve sembol sayısı açık bir ayarla sınırlandırılır.
"""
import json
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


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_universe(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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
    suffix = os.getenv("TWELVE_DATA_BIST_SUFFIX", ":BIST") if market == "BIST" else ""
    requested = [f"{symbol}{suffix}" if suffix and ":" not in symbol else symbol for symbol in selected]
    payload = _request(endpoint, requested, api_key)
    items = []
    for requested_symbol in requested:
        raw = payload.get(requested_symbol) or payload.get(requested_symbol.split(":")[-1])
        if raw and not raw.get("status") == "error":
            items.append(_normalize(raw, requested_symbol, market))
    return {"market": market, "source": endpoint, "fetched_at": datetime.now(timezone.utc).isoformat(), "row_count": len(items), "items": items, "cache": "miss", "requested_count": len(requested)}


def collect_all(universe_path="data/universe.json", markets=None):
    load_env_file()
    api_key = os.getenv("MARKET_DATA_API_KEY", "").strip()
    if not api_key or api_key.lower() in {"replace-with-twelve-data-key", "your-api-key"}:
        raise TwelveDataError("MARKET_DATA_API_KEY yapılandırılmadı.")
    endpoint = os.getenv("MARKET_DATA_BASE_URL", "https://api.twelvedata.com/eod")
    max_symbols = int(os.getenv("TWELVE_DATA_MAX_SYMBOLS", "120"))
    market_limits = {"BIST": int(os.getenv("TWELVE_DATA_BIST_SYMBOLS", str(max_symbols // 2))), "US": int(os.getenv("TWELVE_DATA_US_SYMBOLS", str(max_symbols - max_symbols // 2)))}
    universe = _read_universe(universe_path)
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "provider": "Twelve Data EOD", "markets": {}, "errors": []}
    selected_markets = tuple(markets or ("BIST", "US"))
    for market in selected_markets:
        symbols = universe.get(market, [])[:market_limits.get(market, 0)]
        try:
            batch = collect_market(market, symbols, endpoint, api_key, len(symbols))
            output["markets"][market] = batch
        except TwelveDataError as exc:
            output["errors"].append(f"{market}: {exc}")
        if market == "BIST" and "US" in selected_markets:
            time.sleep(float(os.getenv("TWELVE_DATA_BATCH_PAUSE_SECONDS", "2")))
    return output
