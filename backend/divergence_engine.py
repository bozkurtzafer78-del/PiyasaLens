"""PiyasaLens ayrışma ve karar motoru (Divergence Engine).

Normalize edilmiş analiz snapshot'larını değerlendirir, değerleme/fiyat ayrışmalarını
ve net potansiyeli hesaplayarak yeni alım ve mevcut pozisyon kararlarını üretir.
"""
from typing import Any, Optional


def calculate_divergence(
    price: Optional[float],
    target: Optional[float],
    buy_low: Optional[float] = None,
    buy_high: Optional[float] = None,
    buy_cost: float = 0.15,
    sell_cost: float = 0.15,
    stop: Optional[float] = None,
    thesis: str = "intact",
    data_status: str = "delayed",
    min_ratio: float = 2.0,
) -> dict[str, Any]:
    """Fiyat, hedef ve alım bandı parametreleri üzerinden karar üretir."""
    if (
        price is None
        or target is None
        or price <= 0
        or target <= 0
        or data_status not in {"demo", "real-time", "delayed", "end-of-day"}
    ):
        return {
            "new_buy": "Veri yetersiz",
            "holding": "Veri yetersiz",
            "net": None,
            "gross": None,
            "risk": None,
            "ratio": None,
            "band_missed": False,
            "reason": "Fiyat, hedef veya veri durumu yetersiz.",
        }

    gross = ((target / price) - 1) * 100
    net = (
        (((target * (1 - sell_cost / 100)) / (price * (1 + buy_cost / 100))) - 1)
        * 100
    )
    stop_price = stop if stop is not None else price * 0.90
    risk = max(0.0, ((price - stop_price) / price) * 100)
    ratio = (max(0.0, net) / risk) if risk > 0 else None

    band_missed = False
    if buy_high is not None and price > buy_high:
        band_missed = True

    reasons = []
    if band_missed:
        reasons.append("Fiyat alım bandının üstünde; yeni giriş koşulu beklenmeli.")
    if net < 5.0:
        reasons.append(f"Net potansiyel %{net:.2f} ile %5 eşiğinin altında.")

    new_buy = "Bekle / İzle"
    if net >= 5.0 and not band_missed and (ratio is None or ratio >= min_ratio):
        new_buy = "Al"
        reasons.append("Net potansiyel ve yapılandırılmış risk/getiri koşulu sağlanıyor.")
    elif not reasons:
        reasons.append("Tek başına %5 eşiği alım için yeterli değil; ek kanıt beklenmeli.")

    holding = "Azalt / Sat" if thesis == "broken" else "Tut"

    return {
        "new_buy": new_buy,
        "holding": holding,
        "gross": round(gross, 2),
        "net": round(net, 2),
        "risk": round(risk, 2),
        "ratio": round(ratio, 2) if ratio is not None else None,
        "band_missed": band_missed,
        "reason": " ".join(reasons),
    }


def analyze(snapshot: Any) -> dict[str, Any]:
    """AnalysisSnapshot nesnesini analiz eder."""
    quote = getattr(snapshot, "quote", None)
    instrument = getattr(snapshot, "instrument", None)
    data_quality = getattr(snapshot, "data_quality", "insufficient")
    fundamentals = getattr(snapshot, "fundamentals", {}) or {}

    if not quote or quote.price is None or data_quality in {"insufficient", "unavailable"}:
        return {
            "decision": "Veri yetersiz",
            "new_buy": "Veri yetersiz",
            "holding": "Veri yetersiz",
            "score": None,
            "net_potential": None,
            "gross_potential": None,
            "risk_reward_ratio": None,
            "reason": "Fiyat veya temel analiz verisi yetersiz.",
            "divergence_pct": None,
        }

    target_price = fundamentals.get("target_price") or fundamentals.get("fair_value")
    if target_price:
        decision_res = calculate_divergence(
            price=quote.price,
            target=target_price,
            buy_low=fundamentals.get("buy_low"),
            buy_high=fundamentals.get("buy_high"),
            data_status=quote.status,
            thesis=fundamentals.get("thesis", "intact"),
        )
        return {
            "decision": decision_res["new_buy"],
            "new_buy": decision_res["new_buy"],
            "holding": decision_res["holding"],
            "score": fundamentals.get("screen_score"),
            "net_potential": decision_res["net"],
            "gross_potential": decision_res["gross"],
            "risk_reward_ratio": decision_res["ratio"],
            "reason": decision_res["reason"],
            "divergence_pct": decision_res["gross"],
        }

    return {
        "decision": "Bekle / İzle",
        "new_buy": "Bekle / İzle",
        "holding": "Tut",
        "score": fundamentals.get("screen_score"),
        "net_potential": None,
        "gross_potential": None,
        "risk_reward_ratio": None,
        "reason": f"{instrument.symbol if instrument else 'Enstrüman'} için fiyat mevcut ancak adil değer / hedef modeli bağlanmamış.",
        "divergence_pct": None,
    }
