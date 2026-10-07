#!/usr/bin/env python3
"""PiyasaLens veri servisi.

Sağlayıcı sözleşmesi bağlanana kadar yalnızca açıkça etiketlenmiş demo veri döndürür.
API anahtarları yalnız sunucu ortamında tutulur; tarayıcıya gönderilmez.
"""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from backend.divergence_engine import analyze
from backend.normalized_schema import AnalysisSnapshot, Evidence, Instrument, Quote
from network_tls import verified_context

CATALOG = [
    {"symbol": "THYAO", "name": "Türk Hava Yolları", "exchange": "BIST", "assetType": "Hisse", "sector": "Ulaştırma", "currency": "TRY", "price": 312.4, "coverage": "demo"},
    {"symbol": "ASELS", "name": "Aselsan", "exchange": "BIST", "assetType": "Hisse", "sector": "Savunma", "currency": "TRY", "price": 184.2, "coverage": "unavailable"},
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "assetType": "Hisse", "sector": "Teknoloji", "currency": "USD", "price": 226.5, "coverage": "unavailable"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "exchange": "NYSE Arca", "assetType": "ETF", "sector": "Endeks ETF", "currency": "USD", "price": 671.8, "coverage": "unavailable"},
]


def load_local_env():
    """Bağımlılık eklemeden yerel .env değerlerini süreç ortamına alır."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


load_local_env()


def provider_configured():
    base_url = os.getenv("MARKET_DATA_BASE_URL", "").strip()
    api_key = os.getenv("MARKET_DATA_API_KEY", "").strip()
    return bool(base_url and api_key and api_key.lower() not in {"replace-with-twelve-data-key", "your-api-key"})


def provider_status():
    configured = provider_configured()
    return {
        "mode": "configured" if configured else "demo",
        "provider": os.getenv("MARKET_DATA_PROVIDER_NAME", "Demo catalog"),
        "realTime": False,
        "lastSuccessfulUpdate": datetime.now(timezone.utc).isoformat(),
        "message": "Sağlayıcı bağlantısı yapılandırılmadı." if not configured else "Sağlayıcı yapılandırması bulundu; uç nokta doğrulaması bekliyor.",
    }


def configured_quote(symbol):
    base_url = os.getenv("MARKET_DATA_BASE_URL")
    api_key = os.getenv("MARKET_DATA_API_KEY")
    if not base_url or not api_key:
        return None
    provider = os.getenv("MARKET_DATA_PROVIDER_NAME", "").lower()
    separator = "&" if "?" in base_url else "?"
    if "twelve" in provider:
        request_url = f"{base_url}{separator}symbol={symbol}&apikey={api_key}"
        request = Request(request_url, headers={"Accept": "application/json"})
    else:
        request = Request(f"{base_url}{separator}symbol={symbol}", headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=10, context=verified_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Sağlayıcı bağlantısı başarısız: {exc}") from exc
    values = data.get("values") or []
    latest = values[0] if values else data
    price = latest.get("close") or latest.get("price")
    as_of = latest.get("datetime") or latest.get("asOf") or latest.get("timestamp")
    if not isinstance(price, (int, float)) or not as_of:
        raise RuntimeError("Sağlayıcı yanıtında price ve asOf alanları zorunlu.")
    return {"symbol": symbol, "price": float(price), "currency": data.get("meta", {}).get("currency", data.get("currency", "USD")), "status": "end-of-day", "asOf": as_of, "source": provider_status()["provider"]}


def build_analysis(symbol):
    """Katalog ve sağlayıcı çıktısını ortak analiz sözleşmesine dönüştürür."""
    normalized_symbol = symbol.upper()
    item = next((x for x in CATALOG if x["symbol"] == normalized_symbol), None)
    if not item:
        return None

    configured = provider_configured()
    if configured:
        quote_data = configured_quote(normalized_symbol)
        quote_status = quote_data["status"]
        quote_source = quote_data.get("source", provider_status()["provider"])
        data_quality = "partial"
        data_gaps = ["Temel finansallar ve KAP/SEC kanıtları bu adaptörde henüz bağlı değil."]
    else:
        quote_data = {
            "symbol": normalized_symbol,
            "price": item["price"] if item["coverage"] == "demo" else None,
            "currency": item["currency"],
            "status": "demo" if item["coverage"] == "demo" else "unavailable",
            "asOf": provider_status()["lastSuccessfulUpdate"] if item["coverage"] == "demo" else None,
            "source": "Demo catalog",
        }
        quote_status = quote_data["status"]
        quote_source = quote_data["source"]
        data_quality = "demo" if item["coverage"] == "demo" else "insufficient"
        data_gaps = ["Gerçek fiyat sağlayıcısı bağlı değil.", "Temel finansallar ve KAP/SEC kanıtları bağlı değil."]

    instrument = Instrument(
        symbol=normalized_symbol,
        name=item["name"],
        market="BIST" if item["exchange"] == "BIST" else "US",
        exchange="XIST" if item["exchange"] == "BIST" else item["exchange"],
        asset_type=item["assetType"],
        currency=quote_data.get("currency") or item["currency"],
        sector=item.get("sector"),
        provider_coverage=item["coverage"],
    )
    quote = Quote(
        symbol=normalized_symbol,
        price=quote_data.get("price"),
        as_of=quote_data.get("asOf"),
        status=quote_status,
        source=quote_source,
        currency=instrument.currency,
    )
    snapshot = AnalysisSnapshot(
        instrument=instrument,
        quote=quote,
        fundamentals={},
        technicals={},
        evidence=[],
        data_quality=data_quality,
        data_gaps=data_gaps,
    )
    return {"snapshot": snapshot.to_dict(), "analysis": analyze(snapshot)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "http://localhost:4173")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            return self._send(provider_status())
        if parsed.path == "/api/instruments":
            query = parse_qs(parsed.query).get("q", [""])[0].lower()
            items = [x for x in CATALOG if not query or query in " ".join(str(x[k]) for k in ("symbol", "name", "exchange", "sector", "assetType")).lower()]
            return self._send({"items": items, "count": len(items), "status": provider_status()})
        if parsed.path == "/api/quote":
            symbol = parse_qs(parsed.query).get("symbol", [""])[0].upper()
            if provider_configured():
                try:
                    return self._send(configured_quote(symbol))
                except RuntimeError as exc:
                    return self._send({"error": str(exc), "status": "provider_error"}, 502)
            item = next((x for x in CATALOG if x["symbol"] == symbol), None)
            if not item:
                return self._send({"error": "Enstrüman katalogda bulunamadı."}, 404)
            if item["coverage"] != "demo":
                return self._send({"error": "Bu enstrüman için gerçek veri sağlayıcısı bağlı değil.", "coverage": item["coverage"], "instrument": item}, 503)
            return self._send({"symbol": symbol, "price": item["price"], "currency": item["currency"], "status": "demo", "asOf": provider_status()["lastSuccessfulUpdate"]})
        if parsed.path == "/api/analysis":
            symbol = parse_qs(parsed.query).get("symbol", [""])[0].upper()
            try:
                result = build_analysis(symbol)
            except RuntimeError as exc:
                return self._send({"error": str(exc), "status": "provider_error"}, 502)
            if not result:
                return self._send({"error": "Enstrüman katalogda bulunamadı."}, 404)
            return self._send(result)
        return self._send({"error": "Endpoint bulunamadı."}, 404)

    def log_message(self, *_args):
        return


def main():
    host = os.getenv("PIYASALENS_DATA_HOST", os.getenv("TRADER_DATA_HOST", "127.0.0.1"))
    port = int(os.getenv("PIYASALENS_DATA_PORT", os.getenv("TRADER_DATA_PORT", "4180")))
    print(f"PiyasaLens Python data service: http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
