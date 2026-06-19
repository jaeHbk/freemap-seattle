from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import slickdeals

FIXTURE = Path(__file__).parent / "fixtures" / "slickdeals_list.html"


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["slickdeals"],
        sources={"slickdeals": {"listing_urls": ["https://slickdeals.example/deals/free"]}},
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_slickdeals_fetch_parses_list(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = slickdeals.fetch(_config())

    assert len(deals) == 3
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "slickdeals" for d in deals)
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    by_id = {d.source_id: d for d in deals}
    assert set(by_id) == {"sd-100001", "sd-100002", "sd-100003"}

    # Two online-only deals -> raw_location None
    assert by_id["sd-100001"].raw_location is None
    assert by_id["sd-100002"].raw_location is None
    assert by_id["sd-100001"].url == "https://slickdeals.example/f/100001-free-audiobook"

    # One physical deal carries the store address
    assert by_id["sd-100003"].raw_location == "1518 6th Ave, Seattle, WA 98101"
    assert by_id["sd-100003"].title == "Free Coffee at Downtown Seattle Store"


def _config_two_urls() -> Config:
    cfg = _config()
    cfg.sources["slickdeals"]["listing_urls"] = [
        "https://slickdeals.example/bad",
        "https://slickdeals.example/deals/free",
    ]
    return cfg


def test_slickdeals_fetch_skips_failing_url(monkeypatch):
    """First URL raises; the second still yields its deals and fetch never raises."""
    html = FIXTURE.read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        if url.endswith("/bad"):
            raise httpx.ConnectError("boom")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = slickdeals.fetch(_config_two_urls())

    assert len(deals) == 3
    assert {d.source_id for d in deals} == {"sd-100001", "sd-100002", "sd-100003"}


def test_slickdeals_fetch_skips_idless_deal(monkeypatch):
    """Articles with no data-deal-id (or no title) are skipped — never emitted
    with an empty source_id, where two would collide on the unique upsert key."""
    html = """
    <div class="deal-list">
      <article class="deal" data-deal-id="sd-1">
        <h2 class="deal-title">Real Deal</h2>
        <a class="deal-url" href="https://slickdeals.example/f/1">x</a>
      </article>
      <article class="deal">
        <h2 class="deal-title">First No-ID</h2>
        <a class="deal-url" href="https://slickdeals.example/f/n1">x</a>
      </article>
      <article class="deal">
        <h2 class="deal-title">Second No-ID</h2>
        <a class="deal-url" href="https://slickdeals.example/f/n2">x</a>
      </article>
      <article class="deal" data-deal-id="sd-no-title"></article>
    </div>
    """

    monkeypatch.setattr(httpx, "get", lambda url, **k: _FakeResponse(html))

    deals = slickdeals.fetch(_config())

    # Only the valid deal survives; both id-less deals and the title-less deal
    # are dropped (otherwise the two id-less ones collide to a single row).
    assert len(deals) == 1
    assert deals[0].source_id == "sd-1"
    assert all(d.source_id and d.title for d in deals)
