# tests/test_geocode.py
from scrapers.contract import Deal
from scrapers.geocode import FakeGeocoder
from scrapers.pipeline import geocode_deal


def _deal(placement, geocode_status, raw_location):
    return Deal(
        source="reddit",
        source_id="abc",
        title="t",
        url="http://x",
        description=None,
        deal_type="free",
        category="food",
        placement=placement,
        lat=None,
        lng=None,
        raw_location=raw_location,
        geocode_status=geocode_status,
        posted_at=None,
        expires_at=None,
    )


def test_fake_geocoder_returns_mapping_hit():
    g = FakeGeocoder({"Capitol Hill": (47.6, -122.3)})
    assert g.geocode("Capitol Hill") == (47.6, -122.3)


def test_fake_geocoder_returns_none_on_miss():
    g = FakeGeocoder({})
    assert g.geocode("Nowhere") is None


def test_geocode_deal_ok_sets_latlng_and_status():
    g = FakeGeocoder({"Capitol Hill": (47.6, -122.3)})
    out = geocode_deal(_deal("physical", "pending", "Capitol Hill"), g)
    assert out.lat == 47.6
    assert out.lng == -122.3
    assert out.geocode_status == "ok"


def test_geocode_deal_failed_keeps_deal_nulls_status_failed():
    g = FakeGeocoder({})  # miss -> None
    out = geocode_deal(_deal("physical", "pending", "Unknown Place"), g)
    assert out.lat is None and out.lng is None
    assert out.geocode_status == "failed"


def test_geocode_deal_skips_online():
    g = FakeGeocoder({"X": (1.0, 2.0)})
    out = geocode_deal(_deal("online", "n/a", None), g)
    assert out.lat is None and out.lng is None
    assert out.geocode_status == "n/a"


def test_geocode_deal_skips_already_resolved_physical():
    g = FakeGeocoder({"X": (9.0, 9.0)})
    d = _deal("physical", "ok", "X")
    d.lat, d.lng = 1.0, 2.0
    out = geocode_deal(d, g)
    # status not "pending" -> unchanged
    assert out.lat == 1.0 and out.lng == 2.0
    assert out.geocode_status == "ok"
