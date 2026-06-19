# tests/test_normalize.py
from datetime import datetime

from scrapers.contract import RawDeal
from scrapers.pipeline import normalize


def _raw(**kw):
    base = dict(source="reddit", source_id="abc", title="t", url="http://x")
    base.update(kw)
    return RawDeal(**base)


def test_normalize_collapses_internal_and_edge_whitespace():
    raw = _raw(title="  Free   Coffee\tat\nCafe  ", description="  hi   there ")
    out = normalize(raw)
    assert out.title == "Free Coffee at Cafe"
    assert out.description == "hi there"


def test_normalize_handles_none_description():
    raw = _raw(description=None)
    out = normalize(raw)
    assert out.description is None


def test_normalize_passes_through_valid_datetimes():
    posted = datetime(2026, 6, 1, 9, 0, 0)
    raw = _raw(posted_at=posted, expires_at=datetime(2026, 7, 1, 0, 0, 0))
    out = normalize(raw)
    assert out.posted_at == posted
    assert out.expires_at == datetime(2026, 7, 1, 0, 0, 0)


def test_normalize_coerces_bad_date_to_none_never_raises():
    raw = _raw(posted_at="not-a-date", expires_at=12345)  # type: ignore[arg-type]
    out = normalize(raw)
    assert out.posted_at is None
    assert out.expires_at is None
    assert out.title == "t"
