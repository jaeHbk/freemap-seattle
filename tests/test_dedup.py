# tests/test_dedup.py
from scrapers.contract import Deal
from scrapers.pipeline import dedup


def _deal(source, source_id, title, raw_location, deal_type="free"):
    return Deal(
        source=source,
        source_id=source_id,
        title=title,
        url=f"http://{source}/{source_id}",
        description=None,
        deal_type=deal_type,
        category="food",
        placement="physical" if raw_location else "online",
        lat=None,
        lng=None,
        raw_location=raw_location,
        geocode_status="pending" if raw_location else "n/a",
        posted_at=None,
        expires_at=None,
    )


def test_dedup_assigns_key_to_every_deal():
    deals = [_deal("reddit", "1", "Free Coffee", "Capitol Hill")]
    out = dedup(deals)
    assert out[0].dedup_key is not None


def test_dedup_same_deal_across_sources_shares_key():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill")
    b = _deal("slickdeals", "99", "free   COFFEE", "capitol hill")  # whitespace/case differ
    out = dedup([a, b])
    assert out[0].dedup_key == out[1].dedup_key


def test_dedup_different_deal_type_differs():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill", deal_type="free")
    b = _deal("reddit", "2", "Free Coffee", "Capitol Hill", deal_type="bogo")
    out = dedup([a, b])
    assert out[0].dedup_key != out[1].dedup_key


def test_dedup_different_location_differs():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill")
    b = _deal("reddit", "2", "Free Coffee", "Fremont")
    out = dedup([a, b])
    assert out[0].dedup_key != out[1].dedup_key


def test_dedup_does_not_remove_rows():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill")
    b = _deal("slickdeals", "99", "Free Coffee", "Capitol Hill")
    out = dedup([a, b])
    assert len(out) == 2  # collapse happens at API read, not here


def test_dedup_online_deal_uses_none_location_consistently():
    a = _deal("reddit", "1", "Free Ebook", None)
    b = _deal("slickdeals", "5", "free ebook", None)
    out = dedup([a, b])
    assert out[0].dedup_key == out[1].dedup_key
