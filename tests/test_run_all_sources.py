from datetime import datetime
from pathlib import Path

import httpx
import pytest

from scrapers.config import Config
from scrapers.db import connect, init_db, fetch_all_deals
from scrapers.geocode import FakeGeocoder
from scrapers.run import SOURCES, run_all

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 6, 18, 12, 0, 0)


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["reddit", "chains", "slickdeals", "local"],
        sources={
            "reddit": {"subreddits": ["seattle"], "listing_urls": ["https://reddit.example/r/seattle.json"]},
            "chains": {
                "offers_urls": ["https://seattlebeans.example/offers"],
                "branches": {
                    "Capitol Hill": "1429 12th Ave, Seattle, WA 98122",
                    "Ballard": "5402 22nd Ave NW, Seattle, WA 98107",
                    "Fremont": "3501 Fremont Ave N, Seattle, WA 98103",
                },
            },
            "slickdeals": {"listing_urls": ["https://slickdeals.example/deals/free"]},
            "local": {"feed_urls": ["https://localdeals.example/seattle/feed.xml"]},
        },
    )


def _fixture_router():
    """Return an httpx.get replacement that serves the right recorded payload by URL."""
    chains_html = (FIX / "chains_offers.html").read_text(encoding="utf-8")
    slickdeals_html = (FIX / "slickdeals_list.html").read_text(encoding="utf-8")
    local_xml = (FIX / "local_feed.xml").read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        if "seattlebeans" in url:
            return _FakeResponse(chains_html)
        if "slickdeals" in url:
            return _FakeResponse(slickdeals_html)
        if "localdeals" in url:
            return _FakeResponse(local_xml)
        raise AssertionError(f"unexpected URL in test: {url}")

    return fake_get


def test_run_all_one_source_throws_others_still_upsert(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fixture_router())

    conn = connect(":memory:")
    init_db(conn)

    # Geocode every address/neighborhood the fixtures use so physical deals geocode "ok".
    geocoder = FakeGeocoder(
        {
            "1429 12th Ave, Seattle, WA 98122": (47.6097, -122.3160),
            "5402 22nd Ave NW, Seattle, WA 98107": (47.6680, -122.3850),
            "3501 Fremont Ave N, Seattle, WA 98103": (47.6510, -122.3500),
            "1518 6th Ave, Seattle, WA 98101": (47.6110, -122.3370),
            "Capitol Hill, Seattle, WA": (47.6253, -122.3222),
            "5440 Ballard Ave NW, Seattle, WA 98107": (47.6670, -122.3830),
        }
    )

    def boom(config):
        raise RuntimeError("reddit source exploded")

    # Inject: reddit deliberately throws; the other three use the real fetchers.
    injected = {
        "reddit": boom,
        "chains": SOURCES["chains"],
        "slickdeals": SOURCES["slickdeals"],
        "local": SOURCES["local"],
    }

    summary = run_all(_config(), conn, geocoder, NOW, sources=injected)

    # Canonical return shape: one entry per source with the three keys.
    assert set(summary) == {"reddit", "chains", "slickdeals", "local"}
    for entry in summary.values():
        assert set(entry) == {"deals_found", "upserted", "errors"}

    # The throwing source is recorded as errored, 0 upserted — never aborts the run.
    assert summary["reddit"]["errors"] is not None
    assert "exploded" in summary["reddit"]["errors"]
    assert summary["reddit"]["upserted"] == 0

    # The three healthy sources upserted their rows (chains expands 2 offers x 3 branches).
    assert summary["chains"]["errors"] is None
    assert summary["chains"]["upserted"] == 6
    assert summary["slickdeals"]["errors"] is None
    assert summary["slickdeals"]["upserted"] == 3
    assert summary["local"]["errors"] is None
    assert summary["local"]["upserted"] == 2

    # DB holds exactly the survivors' rows: 6 + 3 + 2 = 11, none from reddit.
    rows = fetch_all_deals(conn)
    assert len(rows) == 11
    assert all(r["source"] != "reddit" for r in rows)
