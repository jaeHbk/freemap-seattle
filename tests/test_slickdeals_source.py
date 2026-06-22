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
        sources={"slickdeals": {"listing_urls": ["https://www.dealnews.com/"]}},
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_slickdeals_fetch_parses_dealnews_offers(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = slickdeals.fetch(_config())

    # Only the two OFFER cards with a stable id survive: the ARTICLE card and the
    # id-less OFFER are both dropped.
    assert len(deals) == 2
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "slickdeals" for d in deals)
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    by_id = {d.source_id: d for d in deals}
    assert set(by_id) == {"21846479", "21846466"}

    # Title is decoded from the data-share-*-url `t=` param (URL-encoded),
    # including punctuation (comma, ampersand).
    assert by_id["21846479"].title == "Amazon Early Prime Day Deals"
    assert by_id["21846466"].title == "Ray-Ban, Oakley, & more at Woot"

    # data-offer-url is already absolute — used verbatim as the deal URL.
    assert (
        by_id["21846479"].url
        == "https://www.dealnews.com/Amazon-Early-Prime-Day-Deals/21846479.html"
    )

    # DealNews offers carry no location element -> online deals (list view).
    assert all(d.raw_location is None for d in deals)


def test_slickdeals_fetch_ignores_non_offer_content(monkeypatch):
    """A content card whose data-content-type is not OFFER (e.g. ARTICLE) is not
    a deal and must not be emitted."""
    html = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(httpx, "get", lambda url, **k: _FakeResponse(html))

    deals = slickdeals.fetch(_config())

    assert "99990000" not in {d.source_id for d in deals}  # the ARTICLE card


def _config_two_urls() -> Config:
    cfg = _config()
    cfg.sources["slickdeals"]["listing_urls"] = [
        "https://www.dealnews.com/bad",
        "https://www.dealnews.com/",
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

    assert {d.source_id for d in deals} == {"21846479", "21846466"}


def test_slickdeals_fetch_skips_idless_offer(monkeypatch):
    """OFFER cards with no data-content-id (or no decodable title) are skipped —
    never emitted with an empty source_id, where two would collide on the
    UNIQUE(source, source_id) upsert key."""
    html = """
    <section>
      <div class="content-card">
        <button data-content-id="ok-1" data-content-type="OFFER"
                data-offer-url="https://www.dealnews.com/ok-1.html"
                data-share-twitter-url="https://www.dealnews.com/lw/share.html?s=twitter&amp;t=Real%20Deal"></button>
      </div>
      <div class="content-card">
        <button data-content-type="OFFER"
                data-offer-url="https://www.dealnews.com/n1.html"
                data-share-twitter-url="https://www.dealnews.com/lw/share.html?s=twitter&amp;t=First%20No%20ID"></button>
      </div>
      <div class="content-card">
        <button data-content-type="OFFER"
                data-offer-url="https://www.dealnews.com/n2.html"
                data-share-twitter-url="https://www.dealnews.com/lw/share.html?s=twitter&amp;t=Second%20No%20ID"></button>
      </div>
      <div class="content-card">
        <button data-content-id="no-title" data-content-type="OFFER"
                data-offer-url="https://www.dealnews.com/nt.html"></button>
      </div>
    </section>
    """

    monkeypatch.setattr(httpx, "get", lambda url, **k: _FakeResponse(html))

    deals = slickdeals.fetch(_config())

    # Only the valid offer survives; both id-less offers and the title-less offer
    # are dropped (otherwise the two id-less ones collide to a single row).
    assert len(deals) == 1
    assert deals[0].source_id == "ok-1"
    assert all(d.source_id and d.title for d in deals)
