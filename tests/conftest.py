import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

# Repo root = parent of the tests/ directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

# Fixed clock for deterministic freshness assertions across the whole suite.
NOW = datetime(2026, 6, 18, 12, 0, 0)


@pytest.fixture
def now():
    """A fixed 'now' so freshness tests never depend on the wall clock."""
    return NOW


@pytest.fixture
def conn():
    """In-memory SQLite connection with the committed schema applied.

    row_factory = sqlite3.Row so rows are accessible by column name, matching
    what scrapers.db.connect() produces.
    """
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_PATH.read_text())
    yield connection
    connection.close()


from datetime import timedelta

import pytest

from scrapers.db import init_db

# Alias of the canonical NOW (defined in M1) that the API tests pin get_now() to.
# Same value — do NOT redefine a different datetime; keep one source of truth.
FIXED_NOW = NOW  # NOW = datetime(2026, 6, 18, 12, 0, 0) from Milestone 1


def _insert_deal(conn, **cols):
    """Insert one fully-specified deals row. Caller passes every column we seed."""
    keys = list(cols.keys())
    placeholders = ", ".join(f":{k}" for k in keys)
    columns = ", ".join(keys)
    conn.execute(
        f"INSERT INTO deals ({columns}) VALUES ({placeholders})",
        cols,
    )


@pytest.fixture
def seeded_db(tmp_path):
    """A temp deals.db seeded with deterministic rows for API tests.

    Rows (relative to FIXED_NOW = 2026-06-18 12:00:00):
      id=1  active physical food/free      in-bbox  (Capitol Hill)
      id=2  active physical retail/bogo    OUT-of-bbox (far east lng)
      id=3  stale  physical food/free      in-bbox  last_seen 48h ago
      id=4  expired physical event/other   in-bbox  expires_at 1h ago
      id=5  active online food/free        no lat/lng, geocode_status n/a
      id=6  active physical food/free      in-bbox, FAILED geocode (no lat/lng)
      id=7  active physical food/free      in-bbox, SAME dedup_key as id=1 (alt url)
    """
    db_file = tmp_path / "deals.db"
    # NOTE: open with check_same_thread=False (mirroring scrapers.db.connect's
    # row_factory) because FastAPI's TestClient dispatches endpoint handlers on a
    # threadpool worker thread while this connection is created on the test thread.
    # Reusing one open connection (as the API tests' _override_conn requires)
    # otherwise raises sqlite3.ProgrammingError ("created in a thread ..."). This is
    # a test-only accommodation; production code path is untouched.
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    fresh = (FIXED_NOW - timedelta(hours=1)).isoformat()        # within stale window
    stale_seen = (FIXED_NOW - timedelta(hours=48)).isoformat()  # older than 24h
    expired_at = (FIXED_NOW - timedelta(hours=1)).isoformat()
    future = (FIXED_NOW + timedelta(days=30)).isoformat()
    posted = (FIXED_NOW - timedelta(hours=2)).isoformat()

    # id=1 active physical food/free, in-bbox, dedup_key "k1"
    _insert_deal(
        conn, id=1, source="reddit", source_id="r1", dedup_key="k1",
        title="Free coffee Capitol Hill", url="https://example.com/r1",
        description="free drip", deal_type="free", category="food",
        placement="physical", lat=47.62, lng=-122.32, raw_location="Capitol Hill",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=2 active physical retail/bogo, OUT of bbox (lng far east)
    _insert_deal(
        conn, id=2, source="slickdeals", source_id="s2", dedup_key="k2",
        title="BOGO shoes", url="https://example.com/s2",
        description="buy one get one", deal_type="bogo", category="retail",
        placement="physical", lat=47.60, lng=-121.00, raw_location="Bellevue",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=3 stale physical food/free, in-bbox, last_seen 48h ago
    _insert_deal(
        conn, id=3, source="reddit", source_id="r3", dedup_key="k3",
        title="Free pizza slice", url="https://example.com/r3",
        description="free pizza", deal_type="free", category="food",
        placement="physical", lat=47.61, lng=-122.33, raw_location="Ballard",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=stale_seen, status="active",
    )
    # id=4 expired physical event/other, in-bbox, expires_at 1h ago
    _insert_deal(
        conn, id=4, source="local", source_id="l4", dedup_key="k4",
        title="Free festival entry", url="https://example.com/l4",
        description="festival", deal_type="other", category="event",
        placement="physical", lat=47.63, lng=-122.34, raw_location="Fremont",
        geocode_status="ok", posted_at=posted, expires_at=expired_at,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=5 active online food/free, no coords
    _insert_deal(
        conn, id=5, source="slickdeals", source_id="s5", dedup_key="k5",
        title="Free meal kit code", url="https://example.com/s5",
        description="online code", deal_type="free", category="food",
        placement="online", lat=None, lng=None, raw_location=None,
        geocode_status="n/a", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=6 active physical food/free, FAILED geocode, in-bbox conceptually but no coords
    _insert_deal(
        conn, id=6, source="reddit", source_id="r6", dedup_key="k6",
        title="Free burrito somewhere", url="https://example.com/r6",
        description="free burrito", deal_type="free", category="food",
        placement="physical", lat=None, lng=None, raw_location="near the thing",
        geocode_status="failed", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=7 active physical food/free, in-bbox, SAME dedup_key as id=1 -> collapses
    _insert_deal(
        conn, id=7, source="slickdeals", source_id="s7", dedup_key="k1",
        title="Free coffee Capitol Hill", url="https://example.com/s7",
        description="free drip alt", deal_type="free", category="food",
        placement="physical", lat=47.62, lng=-122.32, raw_location="Capitol Hill",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    conn.commit()
    yield conn, str(db_file)
    conn.close()
