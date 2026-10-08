"""Optional sourced fundamentals; percentages use percentage points (ROE 20 = 20%)."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from network_tls import verified_context

METRICS = ('pe', 'roe', 'revenue_growth', 'debt_to_equity', 'rsi_14', 'relative_volume', 'market_cap', 'eps', 'net_margin', 'price_book')


def load_metrics():
    url = os.getenv('FUNDAMENTALS_URL', '').strip()
    if url:
        if not url.startswith('https://'):
            raise ValueError('FUNDAMENTALS_URL HTTPS olmalı.')
        headers = {'Accept': 'application/json'}
        if os.getenv('FUNDAMENTALS_API_KEY'):
            headers['Authorization'] = 'Bearer ' + os.environ['FUNDAMENTALS_API_KEY']
        with urlopen(Request(url, headers=headers), timeout=30, context=verified_context()) as response:
            payload = json.load(response)
    else:
        path = Path(os.getenv('FUNDAMENTALS_PATH', 'data/fundamentals.json'))
        payload = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(payload, dict):
        raise ValueError('Temel veri sözleşmesi nesne olmalı.')
    return payload


def enrich(item, metrics):
    record = metrics.get(item['market'] + ':' + item['symbol'])
    if not isinstance(record, dict) or not str(record.get('source', '')).startswith('https://'):
        return item
    try:
        date = datetime.fromisoformat(record['as_of'].replace('Z', '+00:00'))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - date).total_seconds() / 86400
        if not 0 <= age <= float(os.getenv('FUNDAMENTALS_MAX_AGE_DAYS', '180')):
            return item
    except (KeyError, ValueError, TypeError, AttributeError):
        return item
    for key in METRICS:
        if key in {'rsi_14', 'relative_volume'} and age > 4:
            continue
        value = record.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            item[key] = value
    item['fundamentals_source'] = record['source']
    item['fundamentals_as_of'] = record['as_of']
    return item
