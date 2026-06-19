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
