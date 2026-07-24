import sqlite3
from datetime import datetime

from scrapers.contract import Deal
from scrapers import db


def _deal(source_id="r1", title="Free coffee"):
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


def test_connect_uses_row_factory(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    assert conn.row_factory is sqlite3.Row
    conn.close()


def test_init_db_creates_domain_tables(conn):
    # conn fixture already ran the schema, but init_db must be idempotent and
    # also create the tables on a fresh connection.
    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    db.init_db(fresh)
    names = sorted(r[0] for r in fresh.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"
    ))
    assert names == [
        "deal_candidates",
        "deal_evidence",
        "deals",
        "geocode_cache",
        "scrape_runs",
    ]
    fresh.close()


def test_init_db_is_idempotent(conn):
    db.init_db(conn)  # schema already applied by fixture; must not raise
    db.init_db(conn)


def test_init_db_migrates_existing_deals_table():
    legacy = sqlite3.connect(":memory:")
    legacy.execute(
        "CREATE TABLE deals ("
        "id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL, "
        "dedup_key TEXT, lat REAL, lng REAL"
        ")"
    )
    legacy.execute(
        "CREATE TABLE scrape_runs ("
        "id INTEGER PRIMARY KEY, source TEXT NOT NULL, deals_found INTEGER, "
        "errors TEXT"
        ")"
    )

    db.init_db(legacy)

    deal_columns = {
        row[1] for row in legacy.execute("PRAGMA table_info(deals)").fetchall()
    }
    run_columns = {
        row[1]
        for row in legacy.execute("PRAGMA table_info(scrape_runs)").fetchall()
    }
    assert {
        "eligibility",
        "redemption",
        "verified_at",
        "candidate_id",
        "source_tier",
        "verification_status",
        "evidence_count",
        "quality_score",
        "publication_reason",
    } <= deal_columns
    assert {
        "deals_upserted",
        "map_pins",
        "geocode_failures",
        "candidates_staged",
        "candidates_pending",
        "candidates_rejected",
        "duration_ms",
    } <= run_columns
    legacy.close()


def test_upsert_inserts_then_bumps_last_seen(conn):
    t1 = datetime(2026, 6, 18, 10, 0, 0)
    t2 = datetime(2026, 6, 18, 11, 0, 0)

    n1 = db.upsert_deals(conn, [_deal()], t1)
    assert n1 == 1
    row = conn.execute("SELECT * FROM deals WHERE source_id='r1'").fetchone()
    assert row["first_seen"] == t1.isoformat()
    assert row["last_seen"] == t1.isoformat()

    # Re-upsert same (source, source_id): updates, does NOT duplicate.
    n2 = db.upsert_deals(conn, [_deal()], t2)
    assert n2 == 1
    rows = conn.execute("SELECT * FROM deals WHERE source_id='r1'").fetchall()
    assert len(rows) == 1
    assert rows[0]["first_seen"] == t1.isoformat()   # preserved
    assert rows[0]["last_seen"] == t2.isoformat()    # bumped


def test_upsert_persists_structured_deal_terms(conn):
    verified = datetime(2026, 7, 16)
    deal = _deal()
    deal.eligibility = "Rewards members"
    deal.redemption = "Activate the offer in the app"
    deal.verified_at = verified

    assert db.upsert_deals(conn, [deal], verified) == 1

    row = conn.execute("SELECT * FROM deals WHERE source_id='r1'").fetchone()
    assert row["eligibility"] == "Rewards members"
    assert row["redemption"] == "Activate the offer in the app"
    assert row["verified_at"] == verified.isoformat()


def test_record_run_writes_one_row(conn):
    started = datetime(2026, 6, 18, 10, 0, 0)
    finished = datetime(2026, 6, 18, 10, 0, 5)
    db.record_run(
        conn,
        "reddit",
        started,
        finished,
        3,
        None,
        deals_upserted=2,
        map_pins=1,
        geocode_failures=1,
        duration_ms=5000,
    )
    row = conn.execute("SELECT * FROM scrape_runs").fetchone()
    assert row["source"] == "reddit"
    assert row["deals_found"] == 3
    assert row["deals_upserted"] == 2
    assert row["map_pins"] == 1
    assert row["geocode_failures"] == 1
    assert row["duration_ms"] == 5000
    assert row["errors"] is None


def test_collect_source_run_metrics_counts_only_rows_from_current_run(conn):
    now = datetime(2026, 6, 18, 12, 0, 0)
    old = datetime(2026, 6, 18, 10, 0, 0)
    mapped = _deal(source_id="mapped")
    failed = _deal(source_id="failed")
    failed.lat = None
    failed.lng = None
    failed.geocode_status = "failed"
    old_mapped = _deal(source_id="old")

    db.upsert_deals(conn, [mapped, failed], now)
    db.upsert_deals(conn, [old_mapped], old)

    assert db.collect_source_run_metrics(conn, "reddit", now) == {
        "map_pins": 1,
        "geocode_failures": 1,
    }
