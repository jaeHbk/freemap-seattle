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

    # Reddit 403s the identifying config UA, so the source must send a
    # browser-like UA instead — NOT config.user_agent.
    sent_ua = captured["headers"]["User-Agent"]
    assert sent_ua == reddit._BROWSER_USER_AGENT
    assert sent_ua != "FreeMapSeattle/1.0 (test)"
    assert sent_ua.startswith("Mozilla/")
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


def test_fetch_degrades_on_403(monkeypatch):
    # Reddit's documented failure mode: HTTP 403 to a client it dislikes. The
    # source must degrade to 0 found WITHOUT raising, mirroring a real 403 where
    # resp.raise_for_status() throws inside the per-URL try/except.
    class ForbiddenResponse:
        status_code = 403

        def raise_for_status(self):
            request = httpx.Request("GET", "https://www.reddit.com/r/Seattle/.json")
            response = httpx.Response(403, request=request)
            raise httpx.HTTPStatusError(
                "403 Forbidden", request=request, response=response
            )

        def json(self):  # pragma: no cover - never reached after a 403
            raise AssertionError("json() must not be called when status is 403")

    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: ForbiddenResponse())

    deals = reddit.fetch(make_config())
    # Blocked fetch -> 0 found, no exception. The run keeps going.
    assert deals == []


def test_fetch_filters_non_deal_posts(monkeypatch):
    # The plain hot feed mixes real free/BOGO deals with ordinary chatter. The
    # pre-filter must keep deal-signal posts and drop the rest before mapping.
    payload = {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "keep_free",
                        "title": "Free pastries at the Ballard bakery this morning",
                        "url": "https://www.example.com/keep_free",
                        "selftext": "Come grab a freebie.",
                        "created_utc": 1718668800,
                    },
                },
                {
                    "kind": "t3",
                    "data": {
                        "id": "keep_bogo",
                        "title": "BOGO burgers downtown today",
                        "url": "https://www.example.com/keep_bogo",
                        "selftext": "Buy one get one, online order.",
                        "created_utc": 1718668800,
                    },
                },
                {
                    "kind": "t3",
                    "data": {
                        "id": "drop_chatter",
                        "title": "Traffic on I-5 is terrible again",
                        "url": "https://www.example.com/drop_chatter",
                        "selftext": "Just venting about the commute.",
                        "created_utc": 1718668800,
                    },
                },
            ]
        },
    }
    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse(payload))

    deals = reddit.fetch(make_config())
    ids = {d.source_id for d in deals}
    # Deal-signal posts survive; the non-deal post is dropped.
    assert ids == {"keep_free", "keep_bogo"}
