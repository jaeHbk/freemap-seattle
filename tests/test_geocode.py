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


def test_geocode_deal_demotes_on_geocoder_exception():
    """A geocoder that RAISES (e.g. provider 403/timeout) must demote the deal to
    failed-geocode, not let the exception escape — otherwise run_pipeline's per-row
    except drops the whole deal silently. Demote, don't disappear."""
    class _BoomGeocoder:
        def geocode(self, raw_location):
            raise RuntimeError("provider 403")

    out = geocode_deal(_deal("physical", "pending", "102 Pike St, Seattle"), _BoomGeocoder())
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


# ---- real Geocoder cache-first behavior ----
from scrapers.db import connect, init_db
from scrapers.geocode import Geocoder


def _conn():
    c = connect(":memory:")
    init_db(c)
    return c


def test_geocoder_cache_hit_no_live_call(monkeypatch):
    c = _conn()
    c.execute(
        "INSERT INTO geocode_cache(raw_location, lat, lng, status) VALUES (?,?,?,?)",
        ("Capitol Hill", 47.6, -122.3, "ok"),
    )
    c.commit()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)

    def _boom(*a, **k):
        raise AssertionError("live geocode must NOT be called on a cache hit")

    monkeypatch.setattr(g, "_live_geocode", _boom)
    assert g.geocode("Capitol Hill") == (47.6, -122.3)


def test_geocoder_cache_miss_calls_live_then_caches(monkeypatch):
    c = _conn()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)
    calls = []

    def _fake_live(loc):
        calls.append(loc)
        return (1.0, 2.0)

    monkeypatch.setattr(g, "_live_geocode", _fake_live)

    assert g.geocode("Fremont") == (1.0, 2.0)
    assert calls == ["Fremont"]

    # second call is served from cache -> no further live call
    assert g.geocode("Fremont") == (1.0, 2.0)
    assert calls == ["Fremont"]

    row = c.execute(
        "SELECT lat, lng, status FROM geocode_cache WHERE raw_location=?",
        ("Fremont",),
    ).fetchone()
    assert (row["lat"], row["lng"], row["status"]) == (1.0, 2.0, "ok")


def test_geocoder_cached_failure_returns_none_no_live_call(monkeypatch):
    c = _conn()
    c.execute(
        "INSERT INTO geocode_cache(raw_location, lat, lng, status) VALUES (?,?,?,?)",
        ("Bad Place", None, None, "failed"),
    )
    c.commit()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)
    monkeypatch.setattr(
        g, "_live_geocode", lambda loc: (_ for _ in ()).throw(AssertionError("no live"))
    )
    assert g.geocode("Bad Place") is None


def test_geocoder_live_miss_caches_failure(monkeypatch):
    c = _conn()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)
    monkeypatch.setattr(g, "_live_geocode", lambda loc: None)
    assert g.geocode("Ghost Town") is None
    row = c.execute(
        "SELECT status FROM geocode_cache WHERE raw_location=?", ("Ghost Town",)
    ).fetchone()
    assert row["status"] == "failed"


def test_geocoder_respects_max_live_calls_cap(monkeypatch):
    c = _conn()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0, max_live_calls=1)
    monkeypatch.setattr(g, "_live_geocode", lambda loc: (3.0, 4.0))
    assert g.geocode("LocA") == (3.0, 4.0)   # 1st live call allowed
    assert g.geocode("LocB") is None         # cap reached -> no live call, None
