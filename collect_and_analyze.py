#!/usr/bin/env python3
"""BIST/ABD toplu veri + Gemini analiz pipeline'ı.

Örnek:
    python3 collect_and_analyze.py --market all --analyze
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from gemini_analysis import GeminiAnalysisError, analyze_candidates
from market_batch import load_env_file
from twelve_data_batch import TwelveDataError, collect_all

APP_DIR = Path(__file__).resolve().parent


def main():
    load_env_file()
    parser = argparse.ArgumentParser(description="Önbellekli BIST/ABD toplu veri ve Gemini analizi")
    parser.add_argument("--market", choices=["BIST", "US", "all"], default="all")
    parser.add_argument("--analyze", action="store_true", help="Top aday özetini Gemini ile analiz et")
    parser.add_argument("--force", action="store_true", help="24 saatlik cache'i yok say")
    parser.add_argument("--top", type=int, default=int(os.getenv("GEMINI_TOP_N", "30")))
    args = parser.parse_args()
    universe_path = Path(os.getenv("UNIVERSE_PATH", "data/universe.json"))
    if not universe_path.is_absolute():
        universe_path = APP_DIR / universe_path
    try:
        output = collect_all(
            universe_path=universe_path,
            markets=([args.market] if args.market != "all" else None),
        )
        for market, batch in output["markets"].items():
            print(f"{market}: {batch['row_count']} kayıt · {batch.get('source', output['provider'])}")
    except TwelveDataError as exc:
        output = {"generated_at": datetime.now(timezone.utc).isoformat(), "provider": "BIST Data Service + Twelve Data EOD", "markets": {}, "errors": [str(exc)]}
        print(f"Veri sağlayıcısı: HATA · {exc}")
    if args.analyze and output["markets"]:
        try:
            output["gemini"] = analyze_candidates({market: payload["items"] for market, payload in output["markets"].items()}, top_n=args.top)
        except GeminiAnalysisError as exc:
            output["gemini"] = {"status": "error", "error": str(exc)}
            output["errors"].append(str(exc))
    data_dir = APP_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "latest_market.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if output.get("gemini"):
        (data_dir / "latest_strategy.json").write_text(json.dumps(output["gemini"], ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        (data_dir / "latest_strategy.json").write_text(json.dumps({"status": "unavailable", "reason": "Yeterli temel veri olmadan kesin yapay zekâ seçimi yayınlanmaz."}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Çıktı: data/latest_market.json")
    if output.get("gemini"):
        print("AI çıktısı: data/latest_strategy.json")
    return 0 if not output["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
