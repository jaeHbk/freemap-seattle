import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from scrapers.contract import Deal

# Resolve schema.sql relative to this file so init_db works from any CWD.
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
_DEAL_COLUMN_MIGRATIONS = {
    "eligibility": "TEXT",
    "redemption": "TEXT",
    "verified_at": "TIMESTAMP",
}


# --- libSQL/Turso adapter ---------------------------------------------------
# libsql rows are plain tuples (no row["col"]), conn.row_factory is unassignable,
# and named ":param" dict binding raises ValueError. Every read site in this app
# assumes sqlite3.Row semantics. These thin wrappers give libsql cursors the same
# row["col"] / row[0] / .keys() shape and translate ":name" params to qmark, so
# all callers (upsert_deals, fetch_*, Geocoder, record_run, api _row_to_deal)
# work unchanged. Only engaged when TURSO_* env is set; the default is bare
# sqlite3 (see connect()).

# Matches ":name" placeholders but NOT "::" (no double-colon usage in our SQL).
_NAMED_PARAM = re.compile(r"(?<!:):([a-zA-Z_]\w*)")


def _to_qmark(sql: str, params):
    """Translate a {':name': value} dict bind into (qmark_sql, positional_tuple).

    libsql.execute rejects dict params; sqlite3 accepts them. We only translate
    when params is a Mapping — tuple/list params pass straight through.
    """
    if not isinstance(params, dict):
        return sql, params
    order: list[str] = []

    def _sub(m):
        order.append(m.group(1))
        return "?"

    qmark_sql = _NAMED_PARAM.sub(_sub, sql)
    return qmark_sql, tuple(params[name] for name in order)


class _Row:
    """A libsql tuple + its cursor description, exposing sqlite3.Row-style access:
    row["col"], row[0], iteration, len(), and .keys()."""

    __slots__ = ("_values", "_index")

    def __init__(self, values, index: dict[str, int]):
        self._values = values
        self._index = index

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._index[key]]
        return self._values[key]  # int or slice

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._index.keys())

    def __repr__(self):
        return f"_Row({dict(zip(self._index, self._values))!r})"


class _TursoCursor:
    """Wraps a libsql cursor so fetchone/fetchall return _Row objects."""

    def __init__(self, cursor):
        self._cursor = cursor

    def _index(self):
        # description is populated on libsql for SELECTs (incl. COUNT(*) AS alias).
        desc = self._cursor.description or ()
        return {col[0]: i for i, col in enumerate(desc)}

    def fetchone(self):
        values = self._cursor.fetchone()
        if values is None:
            return None
        return _Row(values, self._index())

    def fetchall(self):
        index = self._index()
        return [_Row(v, index) for v in self._cursor.fetchall()]

    def __iter__(self):
        # libsql cursors aren't iterable (no __iter__/__next__), so materialize
        # via fetchall — `for row in conn.execute(...)` must work on the Turso path.
        index = self._index()
        return (_Row(v, index) for v in self._cursor.fetchall())

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _TursoConn:
    """Duck-typed sqlite3.Connection stand-in over a libsql connection.

    Forwards commit/executescript/close/cursor verbatim; execute() translates
    named-dict params to qmark and wraps the returned cursor."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        qsql, qparams = _to_qmark(sql, params)
        return _TursoCursor(self._conn.execute(qsql, qparams))

    def commit(self):
        self._conn.commit()

    def executescript(self, sql):
        return self._conn.executescript(sql)

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        # rollback, cursor, autocommit, etc. fall through to libsql.
        return getattr(self._conn, name)


def connect(path: str):
    """Open a DB connection.

    Default (zero-config): a sqlite3.Connection with row_factory = sqlite3.Row,
    byte-for-byte as before — local dev, :memory:, and all tests are unchanged.

    When BOTH TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set in the environment,
    open the libSQL client instead and wrap it so callers using row["col"] /
    row[0] / named ":param" binds keep working. Return type is duck-typed, not a
    concrete sqlite3.Connection, so the annotation is intentionally loose.
    """
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if os.environ.get("FREEMAP_REQUIRE_TURSO") == "1" and not (url and token):
        raise RuntimeError(
            "Turso credentials are required but TURSO_DATABASE_URL and "
            "TURSO_AUTH_TOKEN are not both set"
        )
    if url and token:
        import libsql

        return _TursoConn(libsql.connect(url, auth_token=token))
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the current schema and upgrade existing deal tables in place."""
    conn.executescript(_SCHEMA_PATH.read_text())
    ensure_schema_migrations(conn)
    conn.commit()


def ensure_schema_migrations(conn) -> None:
    """Add nullable columns introduced after the initial production schema."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(deals)").fetchall()}
    for name, sql_type in _DEAL_COLUMN_MIGRATIONS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {sql_type}")


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
            eligibility, redemption, verified_at,
            deal_type, category, placement, lat, lng, raw_location,
            geocode_status, posted_at, expires_at, first_seen, last_seen, status
        ) VALUES (
            :source, :source_id, :dedup_key, :title, :url, :description,
            :eligibility, :redemption, :verified_at,
            :deal_type, :category, :placement, :lat, :lng, :raw_location,
            :geocode_status, :posted_at, :expires_at, :now, :now, 'active'
        )
        ON CONFLICT(source, source_id) DO UPDATE SET
            dedup_key=excluded.dedup_key,
            title=excluded.title,
            url=excluded.url,
            description=excluded.description,
            eligibility=excluded.eligibility,
            redemption=excluded.redemption,
            verified_at=excluded.verified_at,
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
    now_iso = now.isoformat()
    count = 0
    for d in deals:
        try:
            # Build params INSIDE the try so a malformed Deal (e.g. a non-datetime
            # posted_at that breaks serialization) is skipped per-row rather than
            # aborting the whole batch. _to_db() is the tolerant serializer also
            # used by record_run (single serialization path for the file).
            params = {
                "source": d.source,
                "source_id": d.source_id,
                "dedup_key": d.dedup_key,
                "title": d.title,
                "url": d.url,
                "description": d.description,
                "eligibility": d.eligibility,
                "redemption": d.redemption,
                "verified_at": _to_db(d.verified_at),
                "deal_type": d.deal_type,
                "category": d.category,
                "placement": d.placement,
                "lat": d.lat,
                "lng": d.lng,
                "raw_location": d.raw_location,
                "geocode_status": d.geocode_status,
                "posted_at": _to_db(d.posted_at),
                "expires_at": _to_db(d.expires_at),
                "now": now_iso,
            }
            conn.execute(sql, params)
            count += 1
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
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
    """Return all deal rows (sqlite3.Row objects). FULLY IMPLEMENTED (not a stub).

    Ordered by (first_seen, id) so consumers that collapse dedup_key groups get a
    deterministic primary ("first-seen wins"); SQLite row order is otherwise
    unspecified without an explicit ORDER BY.
    """
    return conn.execute("SELECT * FROM deals ORDER BY first_seen, id").fetchall()


def fetch_deals_in_bbox(conn, bbox) -> list:
    """Return deal rows whose coords fall inside bbox, pushing the filter into SQL.

    bbox = (min_lng, min_lat, max_lng, max_lat). NULL-coord rows are excluded
    (NULL fails the comparison), matching api._in_bbox which returns False for
    deals without coords. BETWEEN is inclusive, matching _in_bbox's <= bounds.
    Ordered like fetch_all_deals (first_seen, id) so dedup-collapse stays
    deterministic. Replaces ONLY the coordinate filter — status/type/category/
    dedup are still applied downstream by the API.
    """
    min_lng, min_lat, max_lng, max_lat = bbox
    return conn.execute(
        "SELECT * FROM deals "
        "WHERE lat IS NOT NULL AND lng IS NOT NULL "
        "AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? "
        "ORDER BY first_seen, id",
        (min_lat, max_lat, min_lng, max_lng),
    ).fetchall()
