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


def test_fetch_skips_non_dict_payload(monkeypatch):
    # Reddit returns a JSON *array* for some endpoints (e.g. comment-thread
    # .json URLs). A non-dict payload must be skipped, not crash the fetch.
    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse([1, 2, 3]))
    deals = reddit.fetch(make_config())
    assert deals == []


def test_fetch_isolates_bad_url_from_good_url(monkeypatch):
    # A bad URL (non-dict payload) processed BEFORE a good one must not abort
    # the loop: the good URL's deals must still be returned. This proves the
    # parsing lives inside the per-URL try/except.
    good_payload = json.loads(FIXTURE.read_text())

    config = make_config()
    config.sources["reddit"]["listing_urls"] = [
        "https://bad.example/comments.json",  # returns a JSON array -> skipped
        "https://good.example/listing.json",  # returns the real listing
    ]

    def fake_get(url, *args, **kwargs):
        if url.startswith("https://bad."):
            return FakeResponse([1, 2, 3])
        return FakeResponse(good_payload)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = reddit.fetch(config)
    # All 3 posts from the good URL survive despite the bad URL coming first.
    assert {d.source_id for d in deals} == {"abc123", "def456", "ghi789"}


def test_extract_location_ignores_substring_false_positives(monkeypatch):
    # Ordinary online deal titles must NOT be flipped to physical by bare
    # substrings like "ave"/"st." matching save/have/gave/leave/street-in-a-word.
    payload = {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "fp1",
                        "title": "Save big on a free ebook bundle",
                        "url": "https://www.example.com/fp1",
                        "selftext": "Have fun, gave it a read, leave a review online.",
                        "created_utc": 1718668800,
                    },
                },
                {
                    "kind": "t3",
                    "data": {
                        "id": "real1",
                        "title": "Free samples at the shop on Pike Street",
                        "url": "https://www.example.com/real1",
                        "selftext": "Stop by 1429 Pike Street for a freebie.",
                        "created_utc": 1718668800,
                    },
                },
            ]
        },
    }
    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse(payload))

    deals = reddit.fetch(make_config())
    by_id = {d.source_id: d for d in deals}

    # False-positive case stays online (no location).
    assert by_id["fp1"].raw_location is None
    # Real "Street" address still resolves to a physical location.
    assert by_id["real1"].raw_location is not None
