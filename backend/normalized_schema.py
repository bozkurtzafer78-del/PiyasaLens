from dataclasses import asdict, dataclass, field


@dataclass
class Instrument:
    symbol: str
    name: str
    market: str
    exchange: str
    asset_type: str
    currency: str
    sector: str | None = None
    provider_coverage: str = 'unavailable'


@dataclass
class Quote:
    symbol: str
    price: float | None
    as_of: str | None
    status: str
    source: str
    currency: str


@dataclass
class Evidence:
    title: str
    url: str
    date: str | None = None
    source: str | None = None


@dataclass
class AnalysisSnapshot:
    instrument: Instrument
    quote: Quote
    fundamentals: dict = field(default_factory=dict)
    technicals: dict = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    data_quality: str = 'insufficient'
    data_gaps: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
