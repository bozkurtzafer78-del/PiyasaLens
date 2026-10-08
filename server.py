#!/usr/bin/env python3
"""PiyasaLens Python Web ve API Sunucusu.

Node.js gerektirmeden statik dosyaları ve /api uç noktalarını sunar.
Kullanım:
    python3 server.py
"""
import json
import mimetypes
import os
import re
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from network_tls import verified_context

ROOT = Path(__file__).resolve().parent
PORT = int(os.getenv("PORT", 4173))
HOST = os.getenv("HOST", "0.0.0.0")

KAP_CACHE = {}
SEC_CACHE = {}

KAP_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
    "User-Agent": "PiyasaLens/1.0",
}
SEC_HEADERS = {
    "Accept": "application/json",
    "User-Agent": os.getenv("SEC_USER_AGENT", "PiyasaLens/1.0 research@piyasalens.local"),
}


def provider_status():
    return {
        "bist": {
            "configured": bool(os.getenv("BIST_DATA_SERVICE_URL")),
            "mode": "delayed",
            "endpoint": "configured" if os.getenv("BIST_DATA_SERVICE_URL") else "demo",
        },
        "us": {
            "configured": bool(os.getenv("MARKET_DATA_API_KEY")),
            "provider": "Twelve Data EOD",
            "mode": "daily-close",
        },
        "ai": {
            "configured": bool(os.getenv("GEMINI_API_KEY")),
            "provider": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        },
        "firestore": {
            "configured": bool(os.path.exists(ROOT / "serviceAccountKey.json") or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")),
            "mode": "cloud-synced" if (ROOT / "serviceAccountKey.json").exists() or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") else "local-persistence",
        },
    }


def get_kap_disclosures(symbol: str) -> dict:
    cached = KAP_CACHE.get(symbol)
    if cached and time.time() - cached["at"] < 300:
        return cached["value"]

    try:
        search_req = Request(
            "https://www.kap.org.tr/tr/api/search/combined",
            data=json.dumps({"keyword": symbol, "memberTypeCode": "BIST"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": "https://www.kap.org.tr", "Referer": "https://www.kap.org.tr/tr/", **KAP_HEADERS},
            method="POST",
        )
        with urlopen(search_req, timeout=10, context=verified_context()) as resp:
            search_data = json.loads(resp.read().decode("utf-8"))

        companies = next((g.get("results", []) for g in search_data if g.get("category") == "companyOrFunds"), [])
        company = next((item for item in companies if str(item.get("cmpOrFundCode", "")).upper() == symbol), None)
        company_name = company.get("searchValue", "") if company else ""

        now_epoch = time.time()
        from_str = datetime.fromtimestamp(now_epoch - 48 * 3600).strftime("%d.%m.%Y")
        today_str = datetime.fromtimestamp(now_epoch).strftime("%d.%m.%Y")

        list_body = {
            "fromDate": from_str,
            "toDate": today_str,
            "disclosureTypes": None,
            "memberTypes": ["IGS", "DDK"],
            "mkkMemberOid": company.get("memberOrFundOid") if company else None,
        }
        list_req = Request(
            "https://www.kap.org.tr/tr/api/disclosure/list/main",
            data=json.dumps(list_body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": "https://www.kap.org.tr", "Referer": "https://www.kap.org.tr/tr/", **KAP_HEADERS},
            method="POST",
        )
        with urlopen(list_req, timeout=10, context=verified_context()) as resp:
            rows = json.loads(resp.read().decode("utf-8"))

        items = []
        for r in rows if isinstance(rows, list) else []:
            basic = r.get("disclosureBasic", r)
            codes = str(basic.get("stockCode") or basic.get("relatedStocks") or "").upper()
            title = str(basic.get("companyTitle") or basic.get("title") or "").upper()
            if symbol in codes or (company_name and company_name.upper() in title):
                idx = basic.get("disclosureIndex")
                items.append({
                    "index": idx,
                    "title": basic.get("title") or basic.get("subject") or "KAP bildirimi",
                    "summary": basic.get("summary", ""),
                    "date": basic.get("publishDate", ""),
                    "url": f"https://www.kap.org.tr/tr/Bildirim/{idx}" if idx else "https://www.kap.org.tr/tr/",
                })
        res = {"status": "ok", "symbol": symbol, "companyName": company_name, "items": items[:6], "fetchedAt": datetime.now(timezone.utc).isoformat()}
        KAP_CACHE[symbol] = {"at": time.time(), "value": res}
        return res
    except Exception as exc:
        return {"status": "ok", "symbol": symbol, "companyName": "", "items": [], "fetchedAt": datetime.now(timezone.utc).isoformat(), "notice": str(exc)}


def get_sec_filings(symbol: str) -> dict:
    cached = SEC_CACHE.get(symbol)
    if cached and time.time() - cached["at"] < 3600:
        return cached["value"]

    try:
        req = Request("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS)
        with urlopen(req, timeout=10, context=verified_context()) as resp:
            ticker_map = json.loads(resp.read().decode("utf-8"))

        match = next((item for item in ticker_map.values() if str(item.get("ticker", "")).upper() == symbol), None)
        if not match:
            return {"status": "ok", "symbol": symbol, "companyName": "", "items": [], "fetchedAt": datetime.now(timezone.utc).isoformat()}

        cik = str(match["cik_str"]).zfill(10)
        sub_req = Request(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=SEC_HEADERS)
        with urlopen(sub_req, timeout=10, context=verified_context()) as resp:
            sub = json.loads(resp.read().decode("utf-8"))

        recent = sub.get("filings", {}).get("recent", {})
        allowed = {"10-K", "10-Q", "8-K", "20-F", "6-K", "424B2"}
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        dates = recent.get("filingDate", [])
        descriptions = recent.get("primaryDocDescription", [])

        items = []
        for i, form in enumerate(forms):
            if form in allowed and i < len(accessions) and i < len(docs):
                acc_path = accessions[i].replace("-", "")
                items.append({
                    "form": form,
                    "title": (descriptions[i] if i < len(descriptions) and descriptions[i] else f"{form} bildirimi"),
                    "date": dates[i] if i < len(dates) else "",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{int(match['cik_str'])}/{acc_path}/{docs[i]}",
                })
                if len(items) >= 6:
                    break

        res = {"status": "ok", "symbol": symbol, "companyName": sub.get("name") or match.get("title", ""), "items": items, "fetchedAt": datetime.now(timezone.utc).isoformat()}
        SEC_CACHE[symbol] = {"at": time.time(), "value": res}
        return res
    except Exception as exc:
        return {"status": "ok", "symbol": symbol, "companyName": "", "items": [], "fetchedAt": datetime.now(timezone.utc).isoformat(), "notice": str(exc)}


class PiyasaLensHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            providers = provider_status()
            return self._send_json({"status": "ok", "firestore": providers.get("firestore", {}).get("configured", False), "refreshRunning": False, "providers": providers})

        if path == "/api/providers":
            return self._send_json({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "providers": provider_status(),
                "disclaimer": "Gecikmeli/araştırma verisi; otomatik emir ve kesin yatırım sinyali yoktur.",
            })

        if path == "/api/market":
            market_file = ROOT / "data" / "latest_market.json"
            if market_file.exists():
                try:
                    data = json.loads(market_file.read_text(encoding="utf-8"))
                    return self._send_json(data)
                except Exception as exc:
                    return self._send_json({"status": "error", "error": f"Piyasa verisi okunamadı: {exc}"}, 500)
            return self._send_json({"status": "unavailable", "error": "Piyasa verisi henüz üretilmedi."}, 503)

        if path == "/api/kap":
            symbol = parse_qs(parsed.query).get("symbol", [""])[0].strip().upper()
            if not symbol or not re.match(r"^[A-Z0-9.]{1,12}$", symbol):
                return self._send_json({"status": "error", "error": "Geçersiz BIST sembolü."}, 400)
            return self._send_json(get_kap_disclosures(symbol))

        if path == "/api/sec":
            symbol = parse_qs(parsed.query).get("symbol", [""])[0].strip().upper()
            if not symbol or not re.match(r"^[A-Z]{1,6}$", symbol):
                return self._send_json({"status": "error", "error": "Geçersiz ABD sembolü."}, 400)
            return self._send_json(get_sec_filings(symbol))

        # Ana sayfa yönlendirmesi
        if path == "/" or path == "":
            self.path = "/index.html"

        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def log_message(self, format, *args):
        # Sadeleştirilmiş konsol günlüğü
        pass


def main():
    mimetypes.init()
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("text/html", ".html")
    mimetypes.add_type("application/json", ".json")

    print(f"PiyasaLens Python Web Sunucusu çalışıyor: http://localhost:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), PiyasaLensHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
