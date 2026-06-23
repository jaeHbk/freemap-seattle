from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import chains

FIXTURE = Path(__file__).parent / "fixtures" / "chains_offers.html"

# The five venue addresses the live config seeds; the fixture mirrors the real
# tomdouglas.com/happy-hour/ markup (one off-site "Visit" link per venue block).
VENUES = {
    "Half Shell": "2020 Western Ave, Seattle, WA 98121",
    "Palace Kitchen": "2030 5th Ave, Seattle, WA 98121",
    "Neb": "316 Virginia St, Seattle, WA 98121",
    "Serious Pie Downtown": "2001 4th Ave, Seattle, WA 98121",
    "Serious Pie Totem Lake": "12540 120th Ave NE #122, Kirkland, WA 98034",
}


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
                "offers_urls": ["https://www.tomdouglas.com/happy-hour/"],
                "venues": dict(VENUES),
            }
        },
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_chains_fetch_parses_happy_hour_venues(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = chains.fetch(_config())

    # 5 venue blocks -> 5 RawDeals. The intro "See All" + footer "Our Restaurants"
    # buttons (relative hrefs) and the name-less block are all skipped.
    assert len(deals) == 5
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "chains" for d in deals)

    # User-Agent from config was sent
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    # Every deal is physical: raw_location comes from the configured venue map.
    by_title = {d.title: d for d in deals}
    assert set(by_title) == {
        "Half Shell Happy Hour",
        "Palace Kitchen Happy Hour",
        "Neb Happy Hour",
        "Serious Pie Downtown Happy Hour",
        "Serious Pie Totem Lake Happy Hour",
    }
    assert all(d.raw_location for d in deals)
    assert by_title["Half Shell Happy Hour"].raw_location == VENUES["Half Shell"]

    # The off-site Visit URL is the deal url AND the stable source_id.
    half = by_title["Half Shell Happy Hour"]
    assert half.url == "https://www.halfshellseattle.com/menus/#happy-hour/"
    assert half.source_id == half.url
    assert half.description and "oyster" in half.description.lower()

    # source_id is unique per venue so the upsert never collapses two venues —
    # including the two Serious Pie locations that share one host.
    ids = [d.source_id for d in deals]
    assert len(ids) == len(set(ids))


def test_chains_fetch_falls_back_to_named_location(monkeypatch):
    """A venue not present in the config `venues` map still surfaces as physical,
    with a "<venue>, Seattle, WA" raw_location the geocoder can resolve by name."""
    html = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(httpx, "get", lambda url, **k: _FakeResponse(html))

    cfg = _config()
    # Drop one venue from the address map; it should fall back, not disappear.
    del cfg.sources["chains"]["venues"]["Neb"]

    deals = chains.fetch(cfg)

    assert len(deals) == 5
    neb = next(d for d in deals if d.title == "Neb Happy Hour")
    assert neb.raw_location == "Neb, Seattle, WA"


def _config_two_urls() -> Config:
    cfg = _config()
    cfg.sources["chains"]["offers_urls"] = [
        "https://www.tomdouglas.com/bad",
        "https://www.tomdouglas.com/happy-hour/",
    ]
    return cfg


def test_chains_fetch_skips_failing_url(monkeypatch):
    """First URL raises; the second still yields its deals and fetch never raises."""
    html = FIXTURE.read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        if url.endswith("/bad"):
            raise httpx.ConnectError("boom")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = chains.fetch(_config_two_urls())

    # The good URL's 5 venues still come through.
    assert len(deals) == 5
    assert all(d.source == "chains" for d in deals)


def test_chains_fetch_skips_relative_and_nameless_blocks(monkeypatch):
    """Buttons with a relative href (intro/footer nav) and an external Visit link
    with no <h2> venue name are both dropped — never emitted as bogus deals."""
    html = """
    <main>
      <section><div>
        <h2>Pick your Vibe</h2>
        <p>Intro blurb.</p>
        <a href="/our-restaurants/" class="btn btn-brand">See All</a>
      </div></section>
      <section><div>
        <h2>Real Venue</h2>
        <p>A real happy hour.</p>
        <a href="https://www.realvenue.example/menus/#hh" class="btn btn-brand">Visit</a>
      </div></section>
      <section><div>
        <p>No heading here.</p>
        <a href="https://www.noname.example/menus/#hh" class="btn btn-brand">Visit</a>
      </div></section>
      <section><div>
        <a href="/contact/" class="btn btn-brand">Footer</a>
      </div></section>
    </main>
    """

    monkeypatch.setattr(httpx, "get", lambda url, **k: _FakeResponse(html))

    deals = chains.fetch(_config())

    # Only the one real venue with both an external Visit link and an <h2> survives.
    assert len(deals) == 1
    assert deals[0].title == "Real Venue Happy Hour"
    assert deals[0].source_id == "https://www.realvenue.example/menus/#hh"
    assert all(d.source_id and d.title for d in deals)


def test_chains_fetch_dedups_repeated_venue_button(monkeypatch):
    """Two 'Visit' buttons pointing at the same venue URL collapse to one deal,
    so they never collide on the UNIQUE(source, source_id) upsert."""
    html = """
    <main>
      <section><div>
        <h2>Twice Linked</h2>
        <p>Happy hour with a duplicated CTA.</p>
        <a href="https://www.twice.example/menus/#hh" class="btn btn-brand">Visit</a>
        <a href="https://www.twice.example/menus/#hh" class="btn btn-brand">Visit</a>
      </div></section>
    </main>
    """

    monkeypatch.setattr(httpx, "get", lambda url, **k: _FakeResponse(html))

    deals = chains.fetch(_config())

    assert len(deals) == 1
    assert deals[0].source_id == "https://www.twice.example/menus/#hh"
