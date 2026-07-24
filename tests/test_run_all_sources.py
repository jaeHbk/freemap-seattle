from datetime import datetime
from pathlib import Path

import httpx
import pytest

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.db import connect, init_db, fetch_all_deals
from scrapers.geocode import FakeGeocoder
from scrapers.run import SOURCES, run_all
from scrapers.sources.places_brand import VerificationError

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
                "offers_urls": ["https://www.tomdouglas.com/happy-hour/"],
                "venues": {
                    "Half Shell": "2020 Western Ave, Seattle, WA 98121",
                    "Palace Kitchen": "2030 5th Ave, Seattle, WA 98121",
                    "Neb": "316 Virginia St, Seattle, WA 98121",
                    "Serious Pie Downtown": "2001 4th Ave, Seattle, WA 98121",
                    "Serious Pie Totem Lake": "12540 120th Ave NE #122, Kirkland, WA 98034",
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
        if "tomdouglas" in url:
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
            # chains: the five Tom Douglas happy-hour venue addresses.
            "2020 Western Ave, Seattle, WA 98121": (47.6109, -122.3430),
            "2030 5th Ave, Seattle, WA 98121": (47.6135, -122.3380),
            "316 Virginia St, Seattle, WA 98121": (47.6140, -122.3420),
            "2001 4th Ave, Seattle, WA 98121": (47.6120, -122.3390),
            "12540 120th Ave NE #122, Kirkland, WA 98034": (47.7160, -122.1830),
            # local fixture addresses/neighborhoods.
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

    # Canonical return shape: one telemetry entry per source.
    assert set(summary) == {"reddit", "chains", "slickdeals", "local"}
    for entry in summary.values():
        assert set(entry) == {
            "deals_found",
            "upserted",
            "map_pins",
            "geocode_failures",
            "candidates_staged",
            "candidates_pending",
            "candidates_rejected",
            "duration_ms",
            "errors",
        }

    # The throwing source is recorded as errored, 0 upserted — never aborts the run.
    assert summary["reddit"]["errors"] is not None
    assert "exploded" in summary["reddit"]["errors"]
    assert summary["reddit"]["upserted"] == 0

    # Healthy broad sources stage their rows without lowering public precision.
    assert summary["chains"]["errors"] is None
    assert summary["chains"]["upserted"] == 0
    assert summary["chains"]["candidates_rejected"] == 5
    assert summary["slickdeals"]["errors"] is None
    # DealNews fixture has 2 valid OFFER cards (an ARTICLE card and an id-less
    # OFFER are correctly skipped).
    assert summary["slickdeals"]["upserted"] == 0
    assert summary["slickdeals"]["candidates_staged"] == 2
    assert summary["local"]["errors"] is None
    assert summary["local"]["upserted"] == 0
    assert summary["local"]["candidates_staged"] == 2

    assert fetch_all_deals(conn) == []
    candidates = conn.execute("SELECT * FROM deal_candidates").fetchall()
    assert len(candidates) == 9
    assert all(r["source"] != "reddit" for r in candidates)


def test_verification_failure_records_error_without_refreshing_existing_rows():
    conn = connect(":memory:")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO deals (
            source, source_id, title, url, deal_type, category, placement,
            geocode_status, status
        ) VALUES (
            'legacy', 'unstaged', 'Old broad result', 'https://example.com/old',
            'other', 'other', 'online', 'n/a', 'active'
        )
        """
    )
    conn.commit()
    config = _config()
    geocoder = FakeGeocoder({})

    def current_terms(config):
        return [
            RawDeal(
                source="places_brand",
                source_id="verified::store",
                title="Free coffee",
                url="https://example.com/terms",
                verified_at=NOW,
            )
        ]

    first = run_all(
        config,
        conn,
        geocoder,
        NOW,
        sources={"places_brand": current_terms},
    )
    assert first["places_brand"]["upserted"] == 1
    rows = fetch_all_deals(conn)
    assert [row["source_id"] for row in rows] == ["verified::store"]
    assert rows[0]["last_seen"] == NOW.isoformat()

    def overdue_terms(config):
        raise VerificationError(
            "places_brand verification failed: Brand: verification overdue"
        )

    later = datetime(2026, 6, 19, 13, 0, 0)
    failed = run_all(
        config,
        conn,
        geocoder,
        later,
        sources={"places_brand": overdue_terms},
    )

    assert "verification overdue" in failed["places_brand"]["errors"]
    assert failed["places_brand"]["upserted"] == 0
    assert fetch_all_deals(conn)[0]["last_seen"] == NOW.isoformat()
