from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import local

FIXTURE = Path(__file__).parent / "fixtures" / "local_feed.xml"


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["local"],
        sources={"local": {"feed_urls": ["https://www.myballard.com/feed/"]}},
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_local_fetch_parses_feed(monkeypatch):
    xml = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(xml)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = local.fetch(_config())

    assert len(deals) == 2
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "local" for d in deals)
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    by_id = {d.source_id: d for d in deals}
    assert set(by_id) == {
        "https://www.myballard.com/?p=342312",
        "https://www.myballard.com/?p=341510",
    }

    # The real MyBallard feed has no location element, so rows are online/list-only.
    assert all(d.raw_location is None for d in deals)
    first = by_id["https://www.myballard.com/?p=342312"]
    assert first.url == (
        "https://www.myballard.com/2026/07/13/"
        "music-dancing-and-lutefisk-a-look-back-at-ballard-music-seafoodfest/"
    )

    # pubDate parsed into posted_at
    assert first.posted_at is not None
    assert first.posted_at.year == 2026
    assert first.posted_at.month == 7
    assert first.posted_at.day == 13


def _config_two_urls() -> Config:
    cfg = _config()
    cfg.sources["local"]["feed_urls"] = [
        "https://www.myballard.com/bad",
        "https://www.myballard.com/feed/",
    ]
    return cfg


def test_local_fetch_skips_failing_url(monkeypatch):
    """First feed raises; the second still yields its items and fetch never raises."""
    xml = FIXTURE.read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        if url.endswith("/bad"):
            raise httpx.ConnectError("boom")
        return _FakeResponse(xml)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = local.fetch(_config_two_urls())

    assert len(deals) == 2
    assert {d.source_id for d in deals} == {
        "https://www.myballard.com/?p=342312",
        "https://www.myballard.com/?p=341510",
    }


def test_local_fetch_skips_malformed_feed(monkeypatch):
    """A malformed XML body (ET.ParseError) for the first feed is skipped; the
    second well-formed feed still parses, and fetch never raises."""
    good_xml = FIXTURE.read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        if url.endswith("/bad"):
            return _FakeResponse("<rss><channel><item><not-closed")
        return _FakeResponse(good_xml)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = local.fetch(_config_two_urls())

    assert len(deals) == 2
    assert {d.source_id for d in deals} == {
        "https://www.myballard.com/?p=342312",
        "https://www.myballard.com/?p=341510",
    }


def test_local_fetch_skips_guidless_item(monkeypatch):
    """Items with no <guid> (or no <title>) are skipped — never emitted with an
    empty source_id, where two would collide on the unique upsert key."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <guid>local-real-1</guid>
        <title>Real Item</title>
        <link>https://localdeals.example/seattle/real-1</link>
      </item>
      <item>
        <title>First No-GUID</title>
        <link>https://localdeals.example/seattle/n1</link>
      </item>
      <item>
        <title>Second No-GUID</title>
        <link>https://localdeals.example/seattle/n2</link>
      </item>
      <item>
        <guid>local-no-title</guid>
        <link>https://localdeals.example/seattle/nt</link>
      </item>
    </channel></rss>"""

    monkeypatch.setattr(httpx, "get", lambda url, **k: _FakeResponse(xml))

    deals = local.fetch(_config())

    # Only the valid item survives; both guid-less items and the title-less item
    # are dropped (otherwise the two guid-less ones collide to a single row).
    assert len(deals) == 1
    assert deals[0].source_id == "local-real-1"
    assert all(d.source_id and d.title for d in deals)
