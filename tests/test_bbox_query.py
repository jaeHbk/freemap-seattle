"""fetch_deals_in_bbox matches an in-memory inclusive coordinate check."""
from scrapers.db import fetch_all_deals, fetch_deals_in_bbox

# Seattle-ish bbox = (minLng, minLat, maxLng, maxLat). Excludes Bellevue (lng -121.0).
BBOX = (-122.45, 47.50, -122.20, 47.75)


def _in_bbox(row, bbox):
    if row["lat"] is None or row["lng"] is None:
        return False
    min_lng, min_lat, max_lng, max_lat = bbox
    return (
        min_lng <= row["lng"] <= max_lng
        and min_lat <= row["lat"] <= max_lat
    )


def test_bbox_sql_matches_in_bbox_on_seeded_rows(seeded_db):
    conn, _ = seeded_db
    sql_ids = [r["id"] for r in fetch_deals_in_bbox(conn, BBOX)]
    expected = [
        r["id"]
        for r in fetch_all_deals(conn)
        if _in_bbox(r, BBOX)
    ]
    assert sql_ids == expected


def test_bbox_sql_excludes_null_coords(seeded_db):
    conn, _ = seeded_db
    ids = {r["id"] for r in fetch_deals_in_bbox(conn, BBOX)}
    # id=5 (online, NULL coords) and id=6 (failed geocode, NULL coords) excluded.
    assert 5 not in ids
    assert 6 not in ids
    # id=2 (Bellevue, lng -121.0) is out of bbox.
    assert 2 not in ids
    # in-bbox physical rows present.
    assert {1, 3, 4, 7}.issubset(ids)


def test_bbox_sql_ordered_first_seen_then_id(seeded_db):
    conn, _ = seeded_db
    rows = fetch_deals_in_bbox(conn, BBOX)
    ids = [r["id"] for r in rows]
    # All seeded rows share first_seen=posted, so the tiebreak is id ascending.
    assert ids == sorted(ids)


def test_bbox_inclusive_bounds(seeded_db):
    conn, _ = seeded_db
    # id=1 sits at (47.62, -122.32). A bbox whose corner exactly equals the point
    # must INCLUDE it (BETWEEN is inclusive, matching _in_bbox's <=).
    tight = (-122.32, 47.62, -122.30, 47.64)
    ids = {r["id"] for r in fetch_deals_in_bbox(conn, tight)}
    assert 1 in ids
