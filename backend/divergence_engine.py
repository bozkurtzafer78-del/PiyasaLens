"""Never turn a quote alone into a trading recommendation."""
import math
from datetime import datetime, timezone


def analyze(snapshot):
    quote = snapshot.quote
    valid = isinstance(quote.price, (int, float)) and math.isfinite(quote.price) and quote.price > 0
    age = None
    try:
        timestamp = datetime.fromisoformat(quote.as_of.replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600
    except (ValueError, TypeError, AttributeError):
        valid = False
    valid = valid and quote.status in {'delayed', 'end-of-day'} and age is not None and 0 <= age <= 96
    complete = valid and snapshot.data_quality == 'complete' and bool(snapshot.fundamentals) and bool(snapshot.evidence)
    return {
        'symbol': snapshot.instrument.symbol,
        'newBuy': 'İncele' if complete else 'Veri yetersiz',
        'holding': 'Veri yetersiz',
        'dataAgeHours': age,
        'reason': 'Kaynak kanıtlarını ve riskleri inceleyin.' if complete else 'Doğrulanmış güncel fiyat, temel metrikler ve kaynak kanıtları gerekli.',
        'data_gaps': snapshot.data_gaps,
    }
