import json
from datetime import datetime
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.db import connect, init_db
from scrapers.geocode import FakeGeocoder
from scrapers.sources import reddit
from scrapers import run

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_sample.json"
NOW = datetime(2026, 6, 18, 12, 0, 0)


def make_config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["reddit"],
        sources={"reddit": {"listing_urls": ["https://www.reddit.com/r/Seattle/.json"]}},
    )


def patch_reddit(monkeypatch):
    payload = json.loads(FIXTURE.read_text())

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse())


def test_run_all_single_source_writes_rows(tmp_path, monkeypatch):
    patch_reddit(monkeypatch)

    db_file = tmp_path / "deals.db"
    conn = connect(str(db_file))
    init_db(conn)

    # Seed the geocoder so the physical coffee deal resolves to a Seattle point.
    selftext = (
        "Victrola Coffee Roasters is giving away free drip coffee all day. "
        "Capitol Hill, Seattle."
    )
    geocoder = FakeGeocoder({selftext: (47.6231, -122.3170)})

    summary = run.run_all(
        make_config(),
        conn,
        geocoder,
        NOW,
        sources={"reddit": reddit.fetch},
    )

    # Canonical return shape.
    assert set(summary.keys()) == {"reddit"}
    assert summary["reddit"]["deals_found"] == 3
    assert summary["reddit"]["upserted"] == 3
    assert summary["reddit"]["errors"] is None

    rows = conn.execute(
        "SELECT source_id, deal_type, placement, geocode_status, lat, lng "
        "FROM deals ORDER BY source_id"
    ).fetchall()
    by_id = {r["source_id"]: r for r in rows}
    assert len(by_id) == 3

    coffee = by_id["abc123"]
    assert coffee["deal_type"] == "free"
    assert coffee["placement"] == "physical"
    assert coffee["geocode_status"] == "ok"
    assert coffee["lat"] == 47.6231
    assert coffee["lng"] == -122.3170

    ebook = by_id["def456"]
    assert ebook["deal_type"] == "free"
    assert ebook["placement"] == "online"

    bogo = by_id["ghi789"]
    assert bogo["deal_type"] == "bogo"
    assert bogo["placement"] == "online"

    # A scrape_runs row was recorded for the source.
    run_rows = conn.execute(
        "SELECT source, deals_found, errors FROM scrape_runs"
    ).fetchall()
    assert len(run_rows) == 1
    assert run_rows[0]["source"] == "reddit"
    assert run_rows[0]["deals_found"] == 3
    assert run_rows[0]["errors"] is None
