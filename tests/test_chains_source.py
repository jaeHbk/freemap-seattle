from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import chains

FIXTURE = Path(__file__).parent / "fixtures" / "chains_offers.html"


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["chains"],
        sources={
            "chains": {
                "offers_urls": ["https://seattlebeans.example/offers"],
                "branches": {
                    "Capitol Hill": "1429 12th Ave, Seattle, WA 98122",
                    "Ballard": "5402 22nd Ave NW, Seattle, WA 98107",
                    "Fremont": "3501 Fremont Ave N, Seattle, WA 98103",
                },
            }
        },
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_chains_fetch_expands_offers_to_branches(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = chains.fetch(_config())

    # 2 offers x 3 branches = 6 RawDeals
    assert len(deals) == 6
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "chains" for d in deals)

    # User-Agent from config was sent
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    # Every branch address shows up as raw_location
    locations = {d.raw_location for d in deals}
    assert locations == {
        "1429 12th Ave, Seattle, WA 98122",
        "5402 22nd Ave NW, Seattle, WA 98107",
        "3501 Fremont Ave N, Seattle, WA 98103",
    }

    # source_id is unique per (offer, branch) so upsert never collapses two branches
    ids = [d.source_id for d in deals]
    assert len(ids) == len(set(ids))

    # The BOGO offer's branch deals carry its title/url/expiry
    bogo = [d for d in deals if d.title == "Buy One Get One Free Latte"]
    assert len(bogo) == 3
    assert bogo[0].url == "https://seattlebeans.example/offers/bogo-latte-2026"
    assert bogo[0].expires_at is not None
    assert bogo[0].expires_at.year == 2026 and bogo[0].expires_at.month == 6
