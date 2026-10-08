"""PiyasaLens birleşik normalize veri şeması.

HisseRadar, USStockRadar, zfinance ve PiyasaLens karar motorunun ortak veri sözleşmesi.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Instrument:
    symbol: str
    name: str
    market: str
    exchange: str
    asset_type: str
    currency: str = "TRY"
    sector: Optional[str] = None
    provider_coverage: str = "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Quote:
    symbol: str
    price: Optional[float] = None
    as_of: Optional[str] = None
    status: str = "unavailable"
    source: str = "unknown"
    currency: str = "TRY"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Evidence:
    source: str
    title: str
    summary: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisSnapshot:
    instrument: Instrument
    quote: Quote
    fundamentals: dict[str, Any] = field(default_factory=dict)
    technicals: dict[str, Any] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    data_quality: str = "insufficient"
    data_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument.to_dict() if hasattr(self.instrument, "to_dict") else asdict(self.instrument),
            "quote": self.quote.to_dict() if hasattr(self.quote, "to_dict") else asdict(self.quote),
            "fundamentals": dict(self.fundamentals),
            "technicals": dict(self.technicals),
            "evidence": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.evidence],
            "data_quality": self.data_quality,
            "data_gaps": list(self.data_gaps),
        }
