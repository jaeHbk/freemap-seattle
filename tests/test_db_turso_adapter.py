"""Pin the Turso/libSQL row-shape + named-param risks.

The local sqlite3 path is the zero-config default; the Turso path is exercised
ONLY when libsql is installed (it is here). Both backends must yield rows that
support BOTH row["col"] and row[0], and both must accept the named-param upsert.

These tests run the SAME query through both backends and assert identical
results, so the libsql adapter can never silently drift from sqlite3.Row.
"""
import sqlite3
from datetime import datetime

import pytest

from scrapers import db
from scrapers.contract import Deal

libsql = pytest.importorskip("libsql")


def _deal():
    return Deal(
        source="reddit", source_id="r1", title="Free coffee", url="http://x",
        description=None, deal_type="free", category="food", placement="physical",
        lat=47.6, lng=-122.3, raw_location="Capitol Hill", geocode_status="ok",
        posted_at=None, expires_at=None, dedup_key="k1",
    )


def _turso_conn(monkeypatch, tmp_path):
    """A db.connect() that takes the Turso branch but points libsql at a LOCAL
    file (libsql.connect accepts a path), so we exercise the adapter without a
    network/token. connect() must consult TURSO_* env to pick the branch.

    Asserts the returned object is NOT a sqlite3.Connection — i.e. the real
    libsql-backed shim, so a test that merely fell through to sqlite3 (which
    natively handles row["col"] + named params) cannot pass by accident."""
    local = str(tmp_path / "turso_local.db")
    monkeypatch.setenv("TURSO_DATABASE_URL", local)
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "dummy-token")
    conn = db.connect(str(tmp_path / "unused-when-turso-env-set.db"))
    assert not isinstance(conn, sqlite3.Connection), (
        "Turso env set but connect() returned a bare sqlite3.Connection; "
        "the libsql adapter branch was not taken."
    )
    return conn


def test_local_connect_unchanged_when_no_turso_env(monkeypatch, tmp_path):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    conn = db.connect(str(tmp_path / "t.db"))
    # byte-for-byte unchanged: a real sqlite3.Connection with sqlite3.Row factory
    assert isinstance(conn, sqlite3.Connection)
    assert conn.row_factory is sqlite3.Row
    conn.close()


def test_required_turso_refuses_local_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("FREEMAP_REQUIRE_TURSO", "1")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="Turso credentials are required"):
        db.connect(str(tmp_path / "must-not-be-created.db"))

    assert not (tmp_path / "must-not-be-created.db").exists()


def test_turso_branch_taken_only_when_both_env_present(monkeypatch, tmp_path):
    # Only URL set -> still local sqlite3 (need BOTH).
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://x")
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    conn = db.connect(str(tmp_path / "t.db"))
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_row_shape_parity_string_and_index_access(monkeypatch, tmp_path):
    """The mandated row-shape test: same query, both backends, identical results
    for row["col"], row[0], .keys(), and a COUNT(*) AS alias."""
    # local sqlite3
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    local = db.connect(str(tmp_path / "local.db"))
    db.init_db(local)
    db.upsert_deals(local, [_deal()], datetime(2026, 6, 18, 10, 0, 0))

    # turso adapter (libsql at a local file)
    turso = _turso_conn(monkeypatch, tmp_path)
    db.init_db(turso)
    db.upsert_deals(turso, [_deal()], datetime(2026, 6, 18, 10, 0, 0))

    for conn in (local, turso):
        row = conn.execute(
            "SELECT id, source, lat FROM deals WHERE source_id='r1'"
        ).fetchone()
        assert row["source"] == "reddit"
        assert row["lat"] == 47.6
        assert row[0] == row["id"]
        assert list(row.keys()) == ["id", "source", "lat"]
        # COUNT(*) AS alias must be reachable by the alias name (api/main.meta).
        n = conn.execute("SELECT COUNT(*) AS n FROM deals").fetchone()
        assert n["n"] == 1
        # .fetchone()["c"] alias used by tests elsewhere
        c = conn.execute("SELECT COUNT(*) AS c FROM deals").fetchone()["c"]
        assert c == 1
    local.close()
    turso.close()


def test_named_param_upsert_roundtrips_through_turso_adapter(monkeypatch, tmp_path):
    """upsert_deals uses :name params; libsql rejects dict params natively, so the
    adapter MUST translate. Verify the write is durable (re-read same connection)."""
    turso = _turso_conn(monkeypatch, tmp_path)
    db.init_db(turso)
    n = db.upsert_deals(turso, [_deal()], datetime(2026, 6, 18, 10, 0, 0))
    assert n == 1
    # durability: re-read in the SAME connection after the explicit commit.
    row = turso.execute("SELECT title, lat FROM deals WHERE source_id='r1'").fetchone()
    assert row["title"] == "Free coffee"
    assert row["lat"] == 47.6
    turso.close()


def test_geocode_cache_read_shape_through_turso_adapter(monkeypatch, tmp_path):
    """Geocoder.geocode reads row["status"]/row["lat"]/row["lng"] from the cache."""
    turso = _turso_conn(monkeypatch, tmp_path)
    db.init_db(turso)
    turso.execute(
        "INSERT INTO geocode_cache(raw_location, lat, lng, status) VALUES (?,?,?,?)",
        ("Capitol Hill", 47.6, -122.3, "ok"),
    )
    turso.commit()
    row = turso.execute(
        "SELECT lat, lng, status FROM geocode_cache WHERE raw_location = ?",
        ("Capitol Hill",),
    ).fetchone()
    assert row["status"] == "ok"
    assert (row["lat"], row["lng"]) == (47.6, -122.3)
    turso.close()
