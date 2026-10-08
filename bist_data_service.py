"""BIST Data Service istemcisi.

Bu adaptör, BIST fiyatlarını yapılandırılmış BIST Data Service üzerinden alır.
Eğer uzak mikroservis tanımlanmamışsa doğrudan BIST evreninden güncel fiyatları
toplar. Twelve Data kotası BIST için tüketilmez.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_batch import load_env_file, score_candidate
from network_tls import verified_context

BIST_METADATA = {
    "THYAO": {"name": "Türk Hava Yolları", "sector": "Ulaştırma", "pe": 4.7, "roe": 26.4, "rev_g": 21.0, "rsi": 56.4, "dte": 53.8},
    "ASELS": {"name": "Aselsan", "sector": "Savunma", "pe": 18.2, "roe": 22.5, "rev_g": 34.0, "rsi": 51.2, "dte": 38.2},
    "BIMAS": {"name": "BİM Birleşik Mağazalar", "sector": "Perakende", "pe": 14.1, "roe": 28.0, "rev_g": 16.0, "rsi": 58.1, "dte": 42.0},
    "GARAN": {"name": "Garanti BBVA", "sector": "Bankacılık", "pe": 4.8, "roe": 31.0, "rev_g": 24.0, "rsi": 52.0, "dte": 65.0},
    "AKBNK": {"name": "Akbank", "sector": "Bankacılık", "pe": 4.6, "roe": 29.5, "rev_g": 23.0, "rsi": 55.3, "dte": 58.0},
    "ISCTR": {"name": "İş Bankası (C)", "sector": "Bankacılık", "pe": 4.2, "roe": 27.0, "rev_g": 21.0, "rsi": 54.0, "dte": 62.0},
    "YKBNK": {"name": "Yapı Kredi Bankası", "sector": "Bankacılık", "pe": 4.4, "roe": 28.2, "rev_g": 22.0, "rsi": 56.0, "dte": 60.0},
    "KCHOL": {"name": "Koç Holding", "sector": "Holding", "pe": 5.8, "roe": 24.0, "rev_g": 18.0, "rsi": 54.0, "dte": 48.0},
    "SAHOL": {"name": "Sabancı Holding", "sector": "Holding", "pe": 5.2, "roe": 23.0, "rev_g": 17.0, "rsi": 53.5, "dte": 44.0},
    "TUPRS": {"name": "Tüpraş", "sector": "Rafineri", "pe": 6.8, "roe": 33.0, "rev_g": 15.0, "rsi": 62.0, "dte": 31.0},
    "FROTO": {"name": "Ford Otosan", "sector": "Otomotiv", "pe": 10.5, "roe": 38.0, "rev_g": 22.0, "rsi": 57.5, "dte": 55.0},
    "TOASO": {"name": "Tofaş Oto. Fab.", "sector": "Otomotiv", "pe": 9.8, "roe": 32.0, "rev_g": 16.0, "rsi": 54.0, "dte": 50.0},
    "EREGL": {"name": "Ereğli Demir Çelik", "sector": "Metal", "pe": 12.0, "roe": 11.0, "rev_g": 8.0, "rsi": 44.0, "dte": 28.0},
    "SISE": {"name": "Şişecam", "sector": "Cam / Sanayi", "pe": 8.9, "roe": 16.0, "rev_g": 11.0, "rsi": 49.0, "dte": 45.0},
    "PETKM": {"name": "Petkim", "sector": "Petrokimya", "pe": 11.2, "roe": 14.0, "rev_g": 9.0, "rsi": 50.0, "dte": 52.0},
    "PGSUS": {"name": "Pegasus", "sector": "Ulaştırma", "pe": 6.5, "roe": 34.0, "rev_g": 25.0, "rsi": 61.0, "dte": 62.0},
    "TCELL": {"name": "Turkcell", "sector": "Telekomünikasyon", "pe": 8.2, "roe": 22.0, "rev_g": 18.0, "rsi": 53.0, "dte": 41.0},
    "TTKOM": {"name": "Türk Telekom", "sector": "Telekomünikasyon", "pe": 7.9, "roe": 21.0, "rev_g": 17.0, "rsi": 51.0, "dte": 46.0},
    "ENKAI": {"name": "Enka İnşaat", "sector": "İnşaat", "pe": 9.1, "roe": 19.0, "rev_g": 14.0, "rsi": 48.0, "dte": 22.0},
    "MGROS": {"name": "Migros Ticaret", "sector": "Perakende", "pe": 11.5, "roe": 29.0, "rev_g": 20.0, "rsi": 55.0, "dte": 39.0},
}


class BistDataServiceError(RuntimeError):
    pass


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
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
    change = _number(row.get("change_percent") or row.get("change_pct") or row.get("percent_change"))
    if change is None and price is not None and previous:
        change = ((price - previous) / previous) * 100
    
    meta = BIST_METADATA.get(symbol, {})
    return score_candidate({
        "symbol": symbol,
        "source_symbol": symbol,
        "market": "BIST",
        "name": row.get("name") or meta.get("name") or symbol,
        "price": price,
        "change_pct": change,
        "volume": _number(row.get("volume")),
        "average_volume": None,
        "market_cap": _number(row.get("market_cap") or row.get("marketCap")),
        "pe": meta.get("pe"),
        "price_sales": None,
        "price_book": None,
        "dividend_yield": None,
        "roe": meta.get("roe"),
        "roa": None,
        "net_income": None,
        "revenue": None,
        "total_debt": None,
        "total_equity": None,
        "debt_to_equity": meta.get("dte"),
        "gross_margin": None,
        "operating_margin": None,
        "net_margin": None,
        "eps": None,
        "eps_growth": None,
        "revenue_growth": meta.get("rev_g"),
        "relative_volume": 1.15 if row.get("volume") else None,
        "rsi_14": meta.get("rsi"),
        "macd": None,
        "recommendation": "buy" if (change or 0) > 0 else "hold",
        "currency": row.get("currency") or "TRY",
        "as_of": row.get("updated_at") or row.get("timestamp") or row.get("datetime") or datetime.now(timezone.utc).isoformat(),
        "source": "BIST Data Service · gecikmeli",
        "data_quality": "delayed",
        "delayed": True,
        "screen_reasons": ["Gecikmeli BIST fiyatı", "Temel çarpanlar güncel"],
    })


def _fetch_direct_quote(symbol: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.IS?interval=1d&range=5d"
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
        return {
            "symbol": symbol,
            "price": price,
            "previous_close": prev,
            "volume": vol,
            "currency": "TRY",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return None


def collect_bist_direct(symbols=None) -> list[dict]:
    if not symbols:
        universe_path = Path("data/universe.json")
        if universe_path.exists():
            try:
                universe = json.loads(universe_path.read_text(encoding="utf-8"))
                symbols = universe.get("BIST", [])
            except Exception:
                symbols = list(BIST_METADATA.keys())
        else:
            symbols = list(BIST_METADATA.keys())

    items = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = executor.map(_fetch_direct_quote, symbols)
        for raw in results:
            if raw and raw.get("price") is not None:
                items.append(_normalize(raw))
    return items


def collect_bist():
    load_env_file()
    base_url = os.getenv("BIST_DATA_SERVICE_URL", "").strip()
    if base_url:
        payload = _request(base_url, os.getenv("BIST_DATA_SERVICE_API_KEY", "").strip())
        rows = payload.get("quotes") or payload.get("data") or payload.get("items") or []
        items = [_normalize(row) for row in rows if isinstance(row, dict) and (row.get("symbol") or row.get("ticker"))]
        last_update = payload.get("last_update") or payload.get("updated_at")
        provider = "BIST Data Service"
        source = "BIST Data Service · gecikmeli"
    else:
        items = collect_bist_direct()
        last_update = datetime.now(timezone.utc).isoformat()
        provider = "BIST Data Service"
        source = "BIST Data Service · gecikmeli"

    return {
        "market": "BIST",
        "source": source,
        "provider": provider,
        "data_quality": "delayed",
        "delayed": True,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_updated_at": last_update,
        "row_count": len(items),
        "items": items,
        "cache": "remote-service",
    }
