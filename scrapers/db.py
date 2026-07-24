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
    "candidate_id": "INTEGER",
    "source_tier": "TEXT",
    "verification_status": "TEXT",
    "evidence_count": "INTEGER",
    "quality_score": "INTEGER",
    "publication_reason": "TEXT",
}
_SCRAPE_RUN_COLUMN_MIGRATIONS = {
    "deals_upserted": "INTEGER",
    "map_pins": "INTEGER",
    "geocode_failures": "INTEGER",
    "candidates_staged": "INTEGER",
    "candidates_pending": "INTEGER",
    "candidates_rejected": "INTEGER",
    "duration_ms": "INTEGER",
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
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(deals)").fetchall()
    }
    for name, sql_type in _DEAL_COLUMN_MIGRATIONS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {name} {sql_type}")

    existing_runs = {
        row[1] for row in conn.execute("PRAGMA table_info(scrape_runs)").fetchall()
    }
    for name, sql_type in _SCRAPE_RUN_COLUMN_MIGRATIONS.items():
        if name not in existing_runs:
            conn.execute(
                f"ALTER TABLE scrape_runs ADD COLUMN {name} {sql_type}"
            )


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
            geocode_status, posted_at, expires_at, first_seen, last_seen, status,
            candidate_id, source_tier, verification_status, evidence_count,
            quality_score, publication_reason
        ) VALUES (
            :source, :source_id, :dedup_key, :title, :url, :description,
            :eligibility, :redemption, :verified_at,
            :deal_type, :category, :placement, :lat, :lng, :raw_location,
            :geocode_status, :posted_at, :expires_at, :now, :now, 'active',
            :candidate_id, :source_tier, :verification_status, :evidence_count,
            :quality_score, :publication_reason
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
            candidate_id=excluded.candidate_id,
            source_tier=excluded.source_tier,
            verification_status=excluded.verification_status,
            evidence_count=excluded.evidence_count,
            quality_score=excluded.quality_score,
            publication_reason=excluded.publication_reason,
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
                "candidate_id": d.candidate_id,
                "source_tier": d.source_tier,
                "verification_status": d.verification_status,
                "evidence_count": d.evidence_count,
                "quality_score": d.quality_score,
                "publication_reason": d.publication_reason,
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
    *,
    deals_upserted: int = 0,
    map_pins: int = 0,
    geocode_failures: int = 0,
    candidates_staged: int = 0,
    candidates_pending: int = 0,
    candidates_rejected: int = 0,
    duration_ms: int | None = None,
) -> None:
    """Write one row to scrape_runs for a single source's run."""
    conn.execute(
        """
        INSERT INTO scrape_runs (
            source, started_at, finished_at, deals_found, deals_upserted,
            map_pins, geocode_failures, candidates_staged,
            candidates_pending, candidates_rejected, duration_ms, errors
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            _to_db(started_at),
            _to_db(finished_at),
            deals_found,
            deals_upserted,
            map_pins,
            geocode_failures,
            candidates_staged,
            candidates_pending,
            candidates_rejected,
            duration_ms,
            errors,
        ),
    )
    conn.commit()


def upsert_candidate(
    conn,
    deal: Deal,
    now: datetime,
    *,
    source_tier: str,
) -> int:
    """Persist a normalized claim before deciding whether it can be published."""
    sql = """
        INSERT INTO deal_candidates (
            source, source_id, dedup_key, title, url, description,
            eligibility, redemption, verified_at, deal_type, category,
            placement, lat, lng, raw_location, geocode_status, posted_at,
            expires_at, source_tier, decision, decision_reason, quality_score,
            first_seen, last_seen
        ) VALUES (
            :source, :source_id, :dedup_key, :title, :url, :description,
            :eligibility, :redemption, :verified_at, :deal_type, :category,
            :placement, :lat, :lng, :raw_location, :geocode_status, :posted_at,
            :expires_at, :source_tier, 'pending', 'evaluation_pending', 0,
            :now, :now
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
            source_tier=excluded.source_tier,
            decision='pending',
            decision_reason='evaluation_pending',
            quality_score=0,
            last_seen=excluded.last_seen
    """
    conn.execute(
        sql,
        {
            "source": deal.source,
            "source_id": deal.source_id,
            "dedup_key": deal.dedup_key,
            "title": deal.title,
            "url": deal.url,
            "description": deal.description,
            "eligibility": deal.eligibility,
            "redemption": deal.redemption,
            "verified_at": _to_db(deal.verified_at),
            "deal_type": deal.deal_type,
            "category": deal.category,
            "placement": deal.placement,
            "lat": deal.lat,
            "lng": deal.lng,
            "raw_location": deal.raw_location,
            "geocode_status": deal.geocode_status,
            "posted_at": _to_db(deal.posted_at),
            "expires_at": _to_db(deal.expires_at),
            "source_tier": source_tier,
            "now": _to_db(now),
        },
    )
    row = conn.execute(
        "SELECT id FROM deal_candidates WHERE source = ? AND source_id = ?",
        (deal.source, deal.source_id),
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError("candidate upsert did not return a row")
    return int(row["id"])


def upsert_evidence(
    conn,
    *,
    candidate_id: int,
    source: str,
    source_id: str,
    evidence_type: str,
    url: str,
    excerpt: str | None,
    content_hash: str,
    observed_at: datetime,
) -> None:
    """Persist one source observation without duplicating unchanged evidence."""
    conn.execute(
        """
        INSERT INTO deal_evidence (
            candidate_id, source, source_id, evidence_type, url, excerpt,
            content_hash, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(candidate_id, content_hash) DO UPDATE SET
            observed_at=excluded.observed_at,
            url=excluded.url,
            excerpt=excluded.excerpt
        """,
        (
            candidate_id,
            source,
            source_id,
            evidence_type,
            url,
            excerpt,
            content_hash,
            _to_db(observed_at),
        ),
    )


def candidate_evidence_stats(conn, dedup_key: str | None) -> dict[str, int]:
    """Return evidence and independent-source counts for a candidate claim."""
    if not dedup_key:
        return {"evidence_count": 0, "source_count": 0}
    row = conn.execute(
        """
        SELECT COUNT(e.id) AS evidence_count,
               COUNT(DISTINCT e.source) AS source_count
        FROM deal_evidence e
        JOIN deal_candidates c ON c.id = e.candidate_id
        WHERE c.dedup_key = ?
        """,
        (dedup_key,),
    ).fetchone()
    return {
        "evidence_count": int(row["evidence_count"] or 0),
        "source_count": int(row["source_count"] or 0),
    }


def update_candidate_decision(
    conn,
    candidate_id: int,
    *,
    decision: str,
    reason: str,
    quality_score: int,
) -> None:
    conn.execute(
        """
        UPDATE deal_candidates
        SET decision = ?, decision_reason = ?, quality_score = ?
        WHERE id = ?
        """,
        (decision, reason, quality_score, candidate_id),
    )


def unpublish_deal(conn, source: str, source_id: str) -> None:
    """Remove a formerly published row when its current claim no longer passes."""
    conn.execute(
        "DELETE FROM deals WHERE source = ? AND source_id = ?",
        (source, source_id),
    )


def unpublish_unstaged_deals(conn) -> int:
    """Remove pre-staging public rows after a successful authoritative refresh."""
    cursor = conn.execute("DELETE FROM deals WHERE candidate_id IS NULL")
    conn.commit()
    return max(0, int(cursor.rowcount or 0))


def collect_staging_metrics(conn, source: str, observed_at) -> dict[str, int]:
    """Count this source run's staged outcomes."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS staged,
               SUM(CASE WHEN decision = 'pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN decision = 'rejected' THEN 1 ELSE 0 END) AS rejected
        FROM deal_candidates
        WHERE source = ? AND last_seen = ?
        """,
        (source, _to_db(observed_at)),
    ).fetchone()
    return {
        "candidates_staged": int(row["staged"] or 0),
        "candidates_pending": int(row["pending"] or 0),
        "candidates_rejected": int(row["rejected"] or 0),
    }


def collect_source_run_metrics(conn, source: str, observed_at) -> dict[str, int]:
    """Count mapped and failed-geocode rows touched by one source run."""
    observed_at = _to_db(observed_at)
    row = conn.execute(
        """
        SELECT
            SUM(
                CASE WHEN placement = 'physical'
                           AND geocode_status = 'ok'
                           AND lat IS NOT NULL
                           AND lng IS NOT NULL
                     THEN 1 ELSE 0 END
            ) AS map_pins,
            SUM(
                CASE WHEN placement = 'physical'
                           AND geocode_status = 'failed'
                     THEN 1 ELSE 0 END
            ) AS geocode_failures
        FROM deals
        WHERE source = ? AND last_seen = ?
        """,
        (source, observed_at),
    ).fetchone()
    return {
        "map_pins": int(row["map_pins"] or 0),
        "geocode_failures": int(row["geocode_failures"] or 0),
    }


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
