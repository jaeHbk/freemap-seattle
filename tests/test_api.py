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
    assert by_source["reddit"]["latest_run"] == {
        "finished_at": "2026-06-18T11:01:00",
        "status": "ok",
        "deals_found": 5,
        "deals_upserted": None,
        "map_pins": None,
        "geocode_failures": None,
        "duration_ms": None,
    }
    assert by_source["slickdeals"]["latest_run"]["status"] == "error"


def test_static_index_served_at_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "FreeMap Seattle" in resp.text


# --- Risky-branch regression tests (review-mandated) ------------------------

def test_bbox_garbage_returns_400(client):
    resp = client.get("/api/deals?bbox=garbage")
    assert resp.status_code == 400


def test_bbox_wrong_arity_returns_400(client):
    resp = client.get("/api/deals?bbox=1,2,3")
    assert resp.status_code == 400


def test_bbox_non_finite_returns_400(client):
    # float("nan") parses fine, so without an explicit finite-check this would
    # silently return results. It must be a 400.
    resp = client.get("/api/deals?bbox=1,2,nan,4")
    assert resp.status_code == 400
    resp_inf = client.get("/api/deals?bbox=1,2,inf,4")
    assert resp_inf.status_code == 400


def test_deal_detail_non_integer_id_returns_422(client):
    resp = client.get("/api/deals/abc")
    assert resp.status_code == 422


def test_aware_expires_at_does_not_500_the_response(client):
    # A stored expires_at with a timezone offset (valid ISO-8601, e.g. produced by
    # the chains source parsing <time datetime="...-07:00">) is re-parsed AWARE by
    # the API. Without coercion in compute_status, comparing it against the naive
    # `now` raises TypeError and 500s the WHOLE /api/deals response. It must not.
    real_conn = app.dependency_overrides[get_conn]()
    posted = FIXED_NOW.isoformat()
    fresh = FIXED_NOW.isoformat()
    # 2026-06-25 23:59 -07:00 is well after FIXED_NOW -> active, in-bbox.
    aware_future = "2026-06-25T23:59:00-07:00"
    real_conn.execute(
        "INSERT INTO deals (source, source_id, dedup_key, title, url, description, "
        "deal_type, category, placement, lat, lng, raw_location, geocode_status, "
        "posted_at, expires_at, first_seen, last_seen, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "chains", "aware1", "kaware", "BOGO latte aware tz",
            "https://example.com/aware1", "desc", "bogo", "food", "physical",
            47.62, -122.30, "Capitol Hill", "ok", posted, aware_future,
            posted, fresh, "active",
        ),
    )
    real_conn.commit()

    resp = client.get(f"/api/deals?bbox={BBOX}")
    assert resp.status_code == 200  # not 500
    by_sid = {d["source_id"]: d for d in resp.json()}
    assert "aware1" in by_sid
    assert by_sid["aware1"]["status"] == "active"


def test_two_null_dedup_key_rows_both_survive(client):
    # Insert two active, in-bbox rows that BOTH have NULL dedup_key. They must
    # NOT collapse together (a falsy/None key means "stands alone").
    real_conn = app.dependency_overrides[get_conn]()
    fresh = (FIXED_NOW).isoformat()
    posted = (FIXED_NOW).isoformat()
    future = "2026-12-31T00:00:00"
    for sid, lng in (("nodup_a", -122.30), ("nodup_b", -122.31)):
        real_conn.execute(
            "INSERT INTO deals (source, source_id, dedup_key, title, url, description, "
            "deal_type, category, placement, lat, lng, raw_location, geocode_status, "
            "posted_at, expires_at, first_seen, last_seen, status) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "reddit", sid, f"No dedup {sid}", f"https://example.com/{sid}",
                "desc", "free", "food", "physical", 47.62, lng, "Capitol Hill",
                "ok", posted, future, posted, fresh, "active",
            ),
        )
    real_conn.commit()

    resp = client.get(f"/api/deals?bbox={BBOX}")
    assert resp.status_code == 200
    sids = {d["source_id"] for d in resp.json()}
    assert "nodup_a" in sids
    assert "nodup_b" in sids  # both survive; NULL dedup_key never collapses
