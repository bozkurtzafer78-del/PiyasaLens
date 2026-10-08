"""Retain a failed market's last successful snapshot without changing its source time."""
import json


def retain_missing_markets(output, path, requested):
    try:
        previous = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return output
    if previous.get('provider') != output.get('provider'):
        return output
    for market in requested:
        old = previous.get('markets', {}).get(market)
        if market not in output['markets'] and isinstance(old, dict) and old.get('items'):
            output['markets'][market] = {**old, 'retained': True}
            output['errors'].append(f'{market}: önceki başarılı fiyat verisi korunuyor; kaynak tarihi güncellenmedi.')
    return output
