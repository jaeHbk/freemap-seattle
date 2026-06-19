from datetime import datetime

from scrapers.contract import RawDeal, Deal


def test_rawdeal_minimal_fields_and_defaults():
    raw = RawDeal(source="reddit", source_id="abc123", title="Free coffee", url="http://x")
    assert raw.source == "reddit"
    assert raw.source_id == "abc123"
    assert raw.title == "Free coffee"
    assert raw.url == "http://x"
    assert raw.description is None
    assert raw.raw_location is None
    assert raw.posted_at is None
    assert raw.expires_at is None
    assert raw.raw == {}


def test_rawdeal_raw_dict_is_per_instance():
    a = RawDeal(source="s", source_id="1", title="t", url="u")
    b = RawDeal(source="s", source_id="2", title="t", url="u")
    a.raw["k"] = "v"
    assert b.raw == {}  # default_factory, not a shared mutable default


def test_deal_required_and_optional_fields():
    deal = Deal(
        source="reddit",
        source_id="abc123",
        title="Free coffee",
        url="http://x",
        description=None,
        deal_type="free",
        category="food",
        placement="physical",
        lat=47.6,
        lng=-122.3,
        raw_location="Capitol Hill",
        geocode_status="ok",
        posted_at=datetime(2026, 6, 18, 9, 0, 0),
        expires_at=None,
    )
    assert deal.deal_type == "free"
    assert deal.placement == "physical"
    assert deal.geocode_status == "ok"
    assert deal.dedup_key is None  # defaults to None until dedup() sets it
