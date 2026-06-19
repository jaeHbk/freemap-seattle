import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_conn, get_now
from tests.conftest import FIXED_NOW


@pytest.fixture
def client(seeded_db):
    """TestClient with get_conn + get_now pinned to the seeded DB and FIXED_NOW."""
    conn, _db_path = seeded_db

    def _override_conn():
        # Reuse the already-open seeded connection; do NOT close per-request.
        return conn

    def _override_now():
        return FIXED_NOW

    app.dependency_overrides[get_conn] = _override_conn
    app.dependency_overrides[get_now] = _override_now
    yield TestClient(app)
    app.dependency_overrides.clear()


# Seattle-ish bbox = minLng,minLat,maxLng,maxLat. Excludes Bellevue (lng -121.00).
BBOX = "-122.45,47.50,-122.20,47.75"


def test_deals_active_in_bbox_excludes_expired_and_out_of_bbox(client):
    resp = client.get(f"/api/deals?bbox={BBOX}")
    assert resp.status_code == 200
    ids = {d["id"] for d in resp.json()}
    # id=1/id=7 collapse to one (dedup_key k1); id=3 is stale (excluded by default);
    # id=4 expired (always excluded); id=2 out of bbox; id=5 online/id=6 failed have
    # no coords so they are not returned by a bbox map query.
    assert 4 not in ids          # expired always excluded
    assert 2 not in ids          # out of bbox
    assert 3 not in ids          # stale excluded by default
    # id=1 present (collapsed primary), id=7 collapsed into it
    assert 1 in ids
    assert 7 not in ids


def test_deals_include_stale_returns_stale_rows(client):
    # Without include_stale, id=3 (stale) is absent.
    base = client.get(f"/api/deals?bbox={BBOX}")
    assert 3 not in {d["id"] for d in base.json()}
    # With include_stale=true, id=3 appears and is marked stale.
    resp = client.get(f"/api/deals?bbox={BBOX}&include_stale=true")
    assert resp.status_code == 200
    by_id = {d["id"]: d for d in resp.json()}
    assert 3 in by_id
    assert by_id[3]["status"] == "stale"
    # Expired (id=4) is STILL excluded even with include_stale.
    assert 4 not in by_id


def test_deals_dedup_collapse_exposes_alt_urls(client):
    resp = client.get(f"/api/deals?bbox={BBOX}")
    by_id = {d["id"]: d for d in resp.json()}
    assert 1 in by_id
    assert 7 not in by_id  # collapsed into id=1
    assert "https://example.com/s7" in by_id[1]["alt_urls"]


def test_deals_type_filter(client):
    # placement=physical + no bbox so we see all non-expired, non-stale physical deals.
    resp = client.get("/api/deals?type=bogo&placement=physical")
    assert resp.status_code == 200
    deals = resp.json()
    assert {d["id"] for d in deals} == {2}  # only the bogo deal (id=2, in or out of bbox irrelevant w/o bbox)
    assert all(d["deal_type"] == "bogo" for d in deals)


def test_deal_detail_returns_full_record(client):
    resp = client.get("/api/deals/5")
    assert resp.status_code == 200
    deal = resp.json()
    assert deal["id"] == 5
    assert deal["placement"] == "online"
    assert deal["deal_type"] == "free"


def test_deal_detail_404_for_missing(client):
    resp = client.get("/api/deals/9999")
    assert resp.status_code == 404


def test_meta_shape_counts_and_last_scrape(client):
    conn, _ = client.app.dependency_overrides  # noqa: not used; keep client active
    # Seed a couple of scrape_runs so meta has data to report.
    real_conn = app.dependency_overrides[get_conn]()
    real_conn.execute(
        "INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors) "
        "VALUES (?, ?, ?, ?, ?)",
        ("reddit", "2026-06-18T06:00:00", "2026-06-18T06:01:00", 4, None),
    )
    real_conn.execute(
        "INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors) "
        "VALUES (?, ?, ?, ?, ?)",
        ("reddit", "2026-06-18T11:00:00", "2026-06-18T11:01:00", 5, None),
    )
    real_conn.execute(
        "INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors) "
        "VALUES (?, ?, ?, ?, ?)",
        ("slickdeals", "2026-06-18T11:00:00", None, 0, "boom"),
    )
    real_conn.commit()

    resp = client.get("/api/meta")
    assert resp.status_code == 200
    meta = resp.json()
    assert "sources" in meta
    by_source = {s["source"]: s for s in meta["sources"]}
    # reddit: total deals currently in deals table + last SUCCESSFUL scrape time
    assert by_source["reddit"]["last_successful_scrape"] == "2026-06-18T11:01:00"
    # slickdeals errored -> last_successful_scrape is None
    assert by_source["slickdeals"]["last_successful_scrape"] is None
    # deal_count per source reflects rows in deals table
    assert by_source["reddit"]["deal_count"] == 3  # ids 1, 3, 6 are reddit
