"""Gemini'ye yalnızca normalize edilmiş aday özetini gönderir."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from network_tls import verified_context


class GeminiAnalysisError(RuntimeError):
    pass


SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "market_summary": {"type": "STRING"},
        "selection_method": {"type": "STRING"},
        "picks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "symbol": {"type": "STRING"}, "rank": {"type": "INTEGER"},
            "decision": {"type": "STRING", "enum": ["izle", "incele", "riskli"]},
            "thesis": {"type": "STRING"}, "risks": {"type": "ARRAY", "items": {"type": "STRING"}},
            "catalysts": {"type": "ARRAY", "items": {"type": "STRING"}}, "confidence": {"type": "INTEGER"}
        }, "required": ["symbol", "rank", "decision", "thesis", "risks", "catalysts", "confidence"]}}
    },
    "required": ["market_summary", "selection_method", "picks"]
}

def _response_text(raw: dict) -> str:
    """Interactions API'nin modern ve geçiş dönemi yanıtlarını metne çevirir."""
    if isinstance(raw.get("output_text"), str):
        return raw["output_text"]

    for key in ("steps", "outputs"):
        entries = raw.get(key) or []
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            if isinstance(entry.get("text"), str):
                return entry["text"]
            content = entry.get("content")
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
            for part in reversed(entry.get("parts") or []):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    return part["text"]

    # Hata/geri dönüş durumlarında eski GenerateContent biçimini de kabul et.
    candidates = raw.get("candidates") or []
    if candidates:
        content = candidates[0].get("content") or {}
        for part in content.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
    raise GeminiAnalysisError("Gemini yanıtında metin çıktısı bulunamadı.")


def analyze_candidates(markets: dict[str, list[dict]], top_n=30):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"status": "skipped", "reason": "GEMINI_API_KEY yapılandırılmadı.", "markets": {}}
    candidates = {market: sorted([item for item in items if item.get("research_ready") and item.get("screen_score") is not None], key=lambda item: item["screen_score"], reverse=True)[:max(1, top_n)] for market, items in markets.items()}
    if not any(candidates.values()):
        return {"status": "skipped", "reason": "Yeterli temel metriğe sahip aday bulunamadı.", "markets": {}}
    prompt = """Sen bir finansal veri özetleyicisisin. Yalnızca aşağıdaki normalize edilmiş veriyi kullan. Eksik veriyi uydurma, kesin al/sat emri verme, belirsizlik ve riskleri açıkça yaz. Her pikin gerekçesi verideki metriklere dayanmalı. Sonucu yalnızca istenen JSON şemasında döndür.\n\nVERİ:\n""" + json.dumps(candidates, ensure_ascii=False)
    model = os.getenv("GEMINI_MODEL", "").strip()
    if not model:
        raise GeminiAnalysisError("GEMINI_MODEL yapılandırılmalı.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
        },
    }
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=25, context=verified_context()) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = _response_text(raw)
        result = json.loads(text)
    except HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (AttributeError, TypeError, ValueError):
            pass
        raise GeminiAnalysisError(f"Gemini analizi başarısız: HTTP {exc.code}{f' · {detail}' if detail else ''}") from exc
    except (URLError, TimeoutError, ValueError, GeminiAnalysisError) as exc:
        raise GeminiAnalysisError(f"Gemini analizi başarısız: {exc}") from exc
    allowed = {item['symbol'] for items in candidates.values() for item in items}
    if not isinstance(result, dict) or not isinstance(result.get('picks'), list):
        raise GeminiAnalysisError('Gemini çıktısı şemaya uymuyor.')
    seen = set()
    for pick in result['picks']:
        if not isinstance(pick, dict) or pick.get('symbol') not in allowed or pick['symbol'] in seen:
            raise GeminiAnalysisError('Gemini çıktısında kapsam dışı/tekrarlı sembol.')
        if pick.get('decision') not in {'izle', 'incele', 'riskli'} or type(pick.get('confidence')) is not int or not 0 <= pick['confidence'] <= 100:
            raise GeminiAnalysisError('Gemini kararı veya güven aralığı geçersiz.')
        if not isinstance(pick.get('thesis'), str) or not all(isinstance(pick.get(key), list) and all(isinstance(value, str) for value in pick[key]) for key in ('risks', 'catalysts')):
            raise GeminiAnalysisError('Gemini açıklama alanları geçersiz.')
        seen.add(pick['symbol'])
    return {"status": "ok", "model": model, "result": result}
