"""BIST Data Service istemcisi.

Bu adaptör, BIST fiyatlarını ayrı bir gecikmeli Render servisi üzerinden alır.
Twelve Data kotası BIST için kullanılmaz. Servis sözleşmesi /all endpoint'idir.
"""
import json
import math
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_batch import load_env_file, score_candidate
from network_tls import verified_context


class BistDataServiceError(RuntimeError):
    pass


def _number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _request(base_url, api_key):
    url = f"{base_url.rstrip('/')}/all"
    query = urlencode({"sort": "symbol"})
    headers = {"Accept": "application/json", "User-Agent": "PiyasaLens/1.0"}
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        request = Request(f"{url}?{query}", headers=headers)
        with urlopen(request, timeout=45, context=verified_context()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise BistDataServiceError(f"BIST Data Service bağlantısı başarısız: {exc}") from exc
    if not isinstance(payload, dict):
        raise BistDataServiceError("BIST Data Service geçersiz JSON döndürdü.")
    if payload.get("status") == "error" or payload.get("error"):
        raise BistDataServiceError(str(payload.get("message") or payload.get("error")))
    return payload


def _normalize(row):
    row = row if isinstance(row, dict) else {}
    symbol = str(row.get("symbol") or row.get("ticker") or "").upper().strip()
    price = _number(row.get("price") or row.get("last") or row.get("close"))
    previous = _number(row.get("previous_close") or row.get("prev_close") or row.get("previousClose"))
    change = next((_number(row[key]) for key in ("change_percent", "change_pct", "percent_change") if row.get(key) is not None), None)
    if change is None and price is not None and previous:
        change = ((price - previous) / previous) * 100
    return score_candidate({
        "symbol": symbol,
        "source_symbol": symbol,
        "market": "BIST",
        "name": row.get("name") or symbol,
        "price": price,
        "change_pct": change,
        "volume": _number(row.get("volume")),
        "average_volume": None,
        "market_cap": _number(row.get("market_cap") or row.get("marketCap")),
        "pe": None, "price_sales": None, "price_book": None, "dividend_yield": None,
        "roe": None, "roa": None, "net_income": None, "revenue": None, "total_debt": None,
        "total_equity": None, "debt_to_equity": None, "gross_margin": None,
        "operating_margin": None, "net_margin": None, "eps": None, "eps_growth": None,
        "revenue_growth": None, "relative_volume": None, "rsi_14": None, "macd": None,
        "recommendation": None,
        "currency": row.get("currency") or "TRY",
        "as_of": row.get("updated_at") or row.get("timestamp") or row.get("datetime"),
        "source": "BIST Data Service · gecikmeli",
        "data_quality": "delayed",
        "delayed": True,
        "screen_reasons": ["Gecikmeli BIST fiyatı", "Temel veri bağlantısı beklemede"],
    })


def collect_bist():
    load_env_file()
    base_url = os.getenv("BIST_DATA_SERVICE_URL", "").strip()
    if not base_url:
        raise BistDataServiceError("BIST_DATA_SERVICE_URL yapılandırılmadı.")
    payload = _request(base_url, os.getenv("BIST_DATA_SERVICE_API_KEY", "").strip())
    rows = payload.get("quotes") or payload.get("data") or payload.get("items") or []
    items = [_normalize(row) for row in rows if isinstance(row, dict) and (row.get("symbol") or row.get("ticker"))]
    items = [item for item in items if item["price"] is not None and item["price"] > 0 and (item["as_of"] or payload.get("last_update") or payload.get("updated_at"))]
    for item in items:
        item["as_of"] = item["as_of"] or payload.get("last_update") or payload.get("updated_at")
    if not items:
        raise BistDataServiceError("Geçerli fiyat ve zaman içeren BIST kaydı yok.")
    return {
        "market": "BIST",
        "source": "BIST Data Service · gecikmeli",
        "provider": "BIST Data Service",
        "data_quality": "delayed",
        "delayed": True,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_updated_at": payload.get("last_update") or payload.get("updated_at"),
        "row_count": len(items),
        "items": items,
        "cache": "remote-service",
    }
