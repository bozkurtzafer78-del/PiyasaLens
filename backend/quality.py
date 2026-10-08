"""Quote freshness based on source time, never on collection time."""
from datetime import datetime, timezone


def fresh_quote(item, max_age_hours=96):
    try:
        value = item.get('as_of')
        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - timestamp).total_seconds() / 3600
        return 0 <= age <= max_age_hours
    except (ValueError, TypeError, AttributeError):
        return False
