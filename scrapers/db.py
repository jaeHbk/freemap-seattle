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


def upsert_deals(conn: sqlite3.Connection, deals: list[Deal], now: datetime) -> int:
    """Insert or update each deal on UNIQUE(source, source_id).

    On insert: first_seen and last_seen = now.
    On conflict: update mutable fields and bump last_seen = now; first_seen preserved.
    Per-row try/except so one bad row never aborts the batch. Returns rows upserted.
    """
    now_iso = now.isoformat()
    upserted = 0
    sql = """
        INSERT INTO deals (
            source, source_id, dedup_key, title, url, description,
            deal_type, category, placement, lat, lng, raw_location,
            geocode_status, posted_at, expires_at, first_seen, last_seen
        ) VALUES (
            :source, :source_id, :dedup_key, :title, :url, :description,
            :deal_type, :category, :placement, :lat, :lng, :raw_location,
            :geocode_status, :posted_at, :expires_at, :now, :now
        )
        ON CONFLICT(source, source_id) DO UPDATE SET
            dedup_key      = excluded.dedup_key,
            title          = excluded.title,
            url            = excluded.url,
            description    = excluded.description,
            deal_type      = excluded.deal_type,
            category       = excluded.category,
            placement      = excluded.placement,
            lat            = excluded.lat,
            lng            = excluded.lng,
            raw_location   = excluded.raw_location,
            geocode_status = excluded.geocode_status,
            posted_at      = excluded.posted_at,
            expires_at     = excluded.expires_at,
            last_seen      = :now
    """
    for deal in deals:
        params = {
            "source": deal.source,
            "source_id": deal.source_id,
            "dedup_key": deal.dedup_key,
            "title": deal.title,
            "url": deal.url,
            "description": deal.description,
            "deal_type": deal.deal_type,
            "category": deal.category,
            "placement": deal.placement,
            "lat": deal.lat,
            "lng": deal.lng,
            "raw_location": deal.raw_location,
            "geocode_status": deal.geocode_status,
            "posted_at": _to_db(deal.posted_at),
            "expires_at": _to_db(deal.expires_at),
            "now": now_iso,
        }
        try:
            conn.execute(sql, params)
            upserted += 1
        except sqlite3.Error:
            # One bad row never aborts the batch.
            continue
    conn.commit()
    return upserted


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


def fetch_all_deals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """SELECT * FROM deals.

    STUB ONLY — replaced with a real, test-first implementation in Milestone 2.
    Present now so the package imports cleanly. Must NOT remain NotImplementedError
    after Milestone 2.
    """
    raise NotImplementedError("fetch_all_deals is implemented in Milestone 2")
