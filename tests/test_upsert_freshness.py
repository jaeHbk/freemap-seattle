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


# ---- upsert_deals behavior ----
from scrapers.contract import Deal
from scrapers.db import upsert_deals, fetch_all_deals


def _deal(source_id, title="Free Coffee"):
    return Deal(
        source="reddit",
        source_id=source_id,
        title=title,
        url="http://x",
        description=None,
        deal_type="free",
        category="food",
        placement="physical",
        lat=47.6,
        lng=-122.3,
        raw_location="Capitol Hill",
        geocode_status="ok",
        posted_at=None,
        expires_at=None,
        dedup_key="k1",
    )


def test_upsert_inserts_new_rows(conn):
    n = upsert_deals(conn, [_deal("a"), _deal("b")], NOW)
    assert n == 2
    rows = fetch_all_deals(conn)
    assert len(rows) == 2


def test_reupsert_same_source_id_does_not_duplicate(conn):
    upsert_deals(conn, [_deal("a")], NOW)
    upsert_deals(conn, [_deal("a", title="Free Coffee UPDATED")], NOW + timedelta(hours=5))
    rows = fetch_all_deals(conn)
    assert len(rows) == 1
    assert rows[0]["title"] == "Free Coffee UPDATED"


def test_reupsert_bumps_last_seen_preserves_first_seen(conn):
    later = NOW + timedelta(hours=5)
    upsert_deals(conn, [_deal("a")], NOW)
    first = fetch_all_deals(conn)[0]
    assert first["first_seen"] == NOW.isoformat()
    assert first["last_seen"] == NOW.isoformat()

    upsert_deals(conn, [_deal("a")], later)
    again = fetch_all_deals(conn)[0]
    assert again["first_seen"] == NOW.isoformat()       # preserved
    assert again["last_seen"] == later.isoformat()      # bumped


def test_upsert_one_bad_row_does_not_abort_batch(conn):
    bad = _deal("good1")
    bad.source = None  # NOT NULL violation -> per-row try/except must skip it
    n = upsert_deals(conn, [bad, _deal("good2")], NOW)
    rows = fetch_all_deals(conn)
    ids = sorted(r["source_id"] for r in rows)
    assert ids == ["good2"]
    assert n == 1


def test_upsert_non_datetime_posted_at_skipped_per_row(conn):
    # A non-datetime posted_at must be caught DURING per-row param/serialization,
    # not abort the whole batch. object() is unbindable by sqlite, so the row
    # fails at conn.execute and is skipped; the valid rows in the same batch persist.
    bad = _deal("bad")
    bad.posted_at = object()  # non-datetime -> per-row skip, never aborts batch
    n = upsert_deals(conn, [_deal("ok1"), bad, _deal("ok2")], NOW)
    rows = fetch_all_deals(conn)
    ids = sorted(r["source_id"] for r in rows)
    assert ids == ["ok1", "ok2"]   # bad row skipped, valid rows persisted
    assert n == 2                  # count reflects only successful upserts
