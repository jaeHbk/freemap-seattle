"""Concurrency tests for the shared-SQLite architecture.

The scraper and the API never call each other — they share only the file-based
SQLite DB (see README). In production the scheduled scrape writes (upsert_deals /
record_run, each committing) while the API serves concurrent reads
(fetch_all_deals) against the same `db_path`. These tests pin that contract:
concurrent writers and readers on one DB file must not raise "database is locked"
(SQLite's default 5s busy-timeout covers our short transactions), must never
expose a torn/partial row, and must leave a consistent committed final state.

In-memory DBs can't model this (each `:memory:` connect is a distinct DB), so
every connection here opens the same file via the production `db.connect()`.
"""

import sqlite3
import threading
from datetime import datetime

from scrapers import db
from scrapers.contract import Deal

NOW = datetime(2026, 6, 18, 12, 0, 0)

NUM_WRITERS = 4
WRITES_PER_WRITER = 30
NUM_READERS = 4
READS_PER_READER = 60


def _deal(source: str, source_id: str) -> Deal:
    """A fully-specified Deal, mirroring tests/test_db_schema.py._deal()."""
    return Deal(
        source=source,
        source_id=source_id,
        title=f"Free coffee {source}/{source_id}",
        url=f"http://x/{source}/{source_id}",
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
        dedup_key=None,  # distinct rows; no dedup collapsing in this test
    )


def test_concurrent_writers_and_readers_no_lock_no_corruption(tmp_path):
    """Writers and readers hammering one DB file: no lock errors, no torn rows,
    and the final committed state holds exactly the rows every writer upserted."""
    db_path = str(tmp_path / "deals.db")
    # Initialize schema once on a dedicated connection before threads start, so
    # readers never race against table creation (an empty-but-valid DB is fine).
    init_conn = db.connect(db_path)
    db.init_db(init_conn)
    init_conn.close()

    errors: list[Exception] = []
    start = threading.Barrier(NUM_WRITERS + NUM_READERS)

    def writer(widx: int) -> None:
        # Each thread owns its connection — sqlite3 connections are not safe to
        # share across threads, and this mirrors the per-process scraper.
        conn = db.connect(db_path)
        try:
            start.wait()
            for i in range(WRITES_PER_WRITER):
                source = f"w{widx}"
                source_id = f"{i}"
                try:
                    db.upsert_deals(conn, [_deal(source, source_id)], NOW)
                    db.record_run(conn, source, NOW, NOW, 1, None)
                except Exception as exc:  # noqa: BLE001 — capture, assert later
                    errors.append(exc)
                    return
        finally:
            conn.close()

    def reader(_ridx: int) -> None:
        conn = db.connect(db_path)
        try:
            start.wait()
            for _ in range(READS_PER_READER):
                try:
                    rows = db.fetch_all_deals(conn)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
                    return
                # Every committed row must be fully formed — a NOT NULL column
                # reading back empty would mean a torn/partial read.
                for row in rows:
                    assert row["source"]
                    assert row["source_id"] != ""
                    assert row["title"]
        finally:
            conn.close()

    threads = [threading.Thread(target=writer, args=(w,)) for w in range(NUM_WRITERS)]
    threads += [threading.Thread(target=reader, args=(r,)) for r in range(NUM_READERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "a worker thread deadlocked"
    # Surface the actual error (e.g. 'database is locked') in the failure message.
    assert not errors, f"concurrent access raised: {errors!r}"

    # Final committed state: every (writer, write) pair is present exactly once.
    conn = db.connect(db_path)
    try:
        deal_count = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        run_count = conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0]
    finally:
        conn.close()
    assert deal_count == NUM_WRITERS * WRITES_PER_WRITER
    assert run_count == NUM_WRITERS * WRITES_PER_WRITER


def test_reader_sees_only_committed_writes(tmp_path):
    """A reader concurrent with a writer observes a monotonically growing,
    never-shrinking deal count — it only ever sees committed transactions, never
    a half-applied batch."""
    db_path = str(tmp_path / "deals.db")
    init_conn = db.connect(db_path)
    db.init_db(init_conn)
    init_conn.close()

    errors: list[Exception] = []
    done = threading.Event()
    total = NUM_WRITERS * WRITES_PER_WRITER

    def writer() -> None:
        conn = db.connect(db_path)
        try:
            for w in range(NUM_WRITERS):
                for i in range(WRITES_PER_WRITER):
                    db.upsert_deals(conn, [_deal(f"w{w}", f"{i}")], NOW)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            done.set()
            conn.close()

    def reader() -> None:
        conn = db.connect(db_path)
        prev = 0
        try:
            # Poll until the writer is done, then one final read to catch the tail.
            while not done.is_set():
                count = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
                assert count >= prev, "deal count went backwards — saw uncommitted state"
                prev = count
            final = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
            assert final >= prev
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            conn.close()

    wt = threading.Thread(target=writer)
    rt = threading.Thread(target=reader)
    rt.start()
    wt.start()
    wt.join(timeout=30)
    rt.join(timeout=30)

    assert not wt.is_alive() and not rt.is_alive(), "a worker thread deadlocked"
    assert not errors, f"concurrent access raised: {errors!r}"

    conn = db.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == total
    finally:
        conn.close()
