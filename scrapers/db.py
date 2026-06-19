import sqlite3
from datetime import datetime
from pathlib import Path

from scrapers.contract import Deal

# Resolve schema.sql relative to this file so init_db works from any CWD.
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def connect(path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory = sqlite3.Row."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Execute db/schema.sql against conn. Idempotent (schema uses IF NOT EXISTS)."""
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.commit()


def _to_db(value):
    """Serialize datetimes to ISO strings for SQLite; pass everything else through."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def upsert_deals(conn, deals: list[Deal], now: datetime) -> int:
    """Insert or update each deal on UNIQUE(source, source_id).

    On conflict: update mutable fields + bump last_seen=:now; first_seen preserved.
    Per-row try/except so one bad row never aborts the batch. Returns rows upserted.
    """
    sql = """
        INSERT INTO deals (
            source, source_id, dedup_key, title, url, description,
            deal_type, category, placement, lat, lng, raw_location,
            geocode_status, posted_at, expires_at, first_seen, last_seen, status
        ) VALUES (
            :source, :source_id, :dedup_key, :title, :url, :description,
            :deal_type, :category, :placement, :lat, :lng, :raw_location,
            :geocode_status, :posted_at, :expires_at, :now, :now, 'active'
        )
        ON CONFLICT(source, source_id) DO UPDATE SET
            dedup_key=excluded.dedup_key,
            title=excluded.title,
            url=excluded.url,
            description=excluded.description,
            deal_type=excluded.deal_type,
            category=excluded.category,
            placement=excluded.placement,
            lat=excluded.lat,
            lng=excluded.lng,
            raw_location=excluded.raw_location,
            geocode_status=excluded.geocode_status,
            posted_at=excluded.posted_at,
            expires_at=excluded.expires_at,
            last_seen=:now
    """
    count = 0
    for d in deals:
        params = {
            "source": d.source,
            "source_id": d.source_id,
            "dedup_key": d.dedup_key,
            "title": d.title,
            "url": d.url,
            "description": d.description,
            "deal_type": d.deal_type,
            "category": d.category,
            "placement": d.placement,
            "lat": d.lat,
            "lng": d.lng,
            "raw_location": d.raw_location,
            "geocode_status": d.geocode_status,
            "posted_at": d.posted_at.isoformat() if d.posted_at else None,
            "expires_at": d.expires_at.isoformat() if d.expires_at else None,
            "now": now.isoformat(),
        }
        try:
            conn.execute(sql, params)
            count += 1
        except sqlite3.Error:
            continue
    conn.commit()
    return count


def record_run(
    conn: sqlite3.Connection,
    source: str,
    started_at,
    finished_at,
    deals_found: int,
    errors: str | None,
) -> None:
    """Write one row to scrape_runs for a single source's run."""
    conn.execute(
        """
        INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors)
        VALUES (?, ?, ?, ?, ?)
        """,
        (source, _to_db(started_at), _to_db(finished_at), deals_found, errors),
    )
    conn.commit()


def fetch_all_deals(conn) -> list:
    """Return all deal rows (sqlite3.Row objects). FULLY IMPLEMENTED (not a stub)."""
    return conn.execute("SELECT * FROM deals").fetchall()
