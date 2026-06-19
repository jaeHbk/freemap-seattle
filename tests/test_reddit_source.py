import json
from datetime import datetime
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import reddit

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_sample.json"


class FakeResponse:
    """Minimal stand-in for httpx.Response: only what reddit.fetch uses."""

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def make_config() -> Config:
    return Config(
        metro="seattle",
        db_path="db/deals.db",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["reddit"],
        sources={"reddit": {"listing_urls": ["https://www.reddit.com/r/Seattle/.json"]}},
    )


def test_fetch_returns_rawdeals(monkeypatch):
    payload = json.loads(FIXTURE.read_text())

    captured = {}

    def fake_get(url, *args, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return FakeResponse(payload)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = reddit.fetch(make_config())

    assert isinstance(deals, list)
    assert len(deals) == 3
    assert all(isinstance(d, RawDeal) for d in deals)

    # User-Agent from config must be forwarded on the outbound request.
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"
    # The configured listing URL must have been used.
    assert captured["url"] == "https://www.reddit.com/r/Seattle/.json"


def test_fetch_maps_fields(monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse(payload))

    deals = reddit.fetch(make_config())
    by_id = {d.source_id: d for d in deals}

    coffee = by_id["abc123"]
    assert coffee.source == "reddit"
    assert coffee.title == "Free coffee at Victrola Coffee on Capitol Hill today only"
    assert coffee.url == "https://www.reddit.com/r/Seattle/comments/abc123/free_coffee/"
    assert coffee.raw_location is not None  # in-store deal carries location text
    assert isinstance(coffee.posted_at, datetime)
    assert coffee.posted_at == datetime.fromtimestamp(1718668800)
    assert coffee.raw["subreddit"] == "Seattle"


def test_fetch_never_raises_on_bad_listing(monkeypatch):
    # A malformed listing (no children) must yield [] rather than crashing,
    # so one bad subreddit response never aborts the source.
    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse({"data": {}}))
    deals = reddit.fetch(make_config())
    assert deals == []
