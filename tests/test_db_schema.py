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


def test_init_db_creates_all_three_tables(conn):
    # conn fixture already ran the schema, but init_db must be idempotent and
    # also create the tables on a fresh connection.
    fresh = sqlite3.connect(":memory:")
    fresh.row_factory = sqlite3.Row
    db.init_db(fresh)
    names = sorted(r[0] for r in fresh.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"
    ))
    assert names == ["deals", "geocode_cache", "scrape_runs"]
    fresh.close()


def test_init_db_is_idempotent(conn):
    db.init_db(conn)  # schema already applied by fixture; must not raise
    db.init_db(conn)


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


def test_record_run_writes_one_row(conn):
    started = datetime(2026, 6, 18, 10, 0, 0)
    finished = datetime(2026, 6, 18, 10, 0, 5)
    db.record_run(conn, "reddit", started, finished, 3, None)
    row = conn.execute("SELECT * FROM scrape_runs").fetchone()
    assert row["source"] == "reddit"
    assert row["deals_found"] == 3
    assert row["errors"] is None
