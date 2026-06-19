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
        sources={"local": {"feed_urls": ["https://localdeals.example/seattle/feed.xml"]}},
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
    assert set(by_id) == {"local-2026-0001", "local-2026-0002"}

    # All local deals are physical -> raw_location populated
    assert by_id["local-2026-0001"].raw_location == "Capitol Hill, Seattle, WA"
    assert by_id["local-2026-0002"].raw_location == "5440 Ballard Ave NW, Seattle, WA 98107"
    assert by_id["local-2026-0001"].url == "https://localdeals.example/seattle/0001-free-scoop"

    # pubDate parsed into posted_at
    assert by_id["local-2026-0001"].posted_at is not None
    assert by_id["local-2026-0001"].posted_at.year == 2026
    assert by_id["local-2026-0001"].posted_at.month == 6
    assert by_id["local-2026-0001"].posted_at.day == 15
