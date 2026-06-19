# tests/test_upsert_freshness.py
from datetime import datetime, timedelta

from scrapers.pipeline import compute_status

NOW = datetime(2026, 6, 18, 12, 0, 0)
STALE_HOURS = 24


def test_status_expired_when_expires_in_past():
    expires = NOW - timedelta(hours=1)
    last_seen = NOW  # fresh, but expiry wins
    assert compute_status(expires, last_seen, NOW, STALE_HOURS) == "expired"


def test_status_active_when_fresh_and_not_expired():
    expires = NOW + timedelta(days=7)
    last_seen = NOW - timedelta(hours=1)
    assert compute_status(expires, last_seen, NOW, STALE_HOURS) == "active"


def test_status_stale_when_last_seen_older_than_threshold():
    last_seen = NOW - timedelta(hours=25)  # > 24h
    assert compute_status(None, last_seen, NOW, STALE_HOURS) == "stale"


def test_status_active_at_exactly_threshold():
    last_seen = NOW - timedelta(hours=24)  # exactly 24h -> NOT > 24h -> active
    assert compute_status(None, last_seen, NOW, STALE_HOURS) == "active"


def test_status_none_expires_is_not_expired():
    last_seen = NOW - timedelta(hours=1)
    assert compute_status(None, last_seen, NOW, STALE_HOURS) == "active"


def test_status_expired_takes_priority_over_stale():
    expires = NOW - timedelta(hours=1)
    last_seen = NOW - timedelta(hours=100)  # also stale, but expired wins
    assert compute_status(expires, last_seen, NOW, STALE_HOURS) == "expired"
