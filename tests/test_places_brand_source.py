"""Tests for the places_brand source: brand offer -> one physical RawDeal per
Seattle storefront. Mirrors test_chains_source.py's fan-out + isolation checks.
No live network: httpx.get is monkeypatched; the google path uses a recorded
Places Text Search JSON fixture."""

import json
from datetime import datetime
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import places_brand

FIXTURE = Path(__file__).parent / "fixtures" / "places_textsearch.json"


def _config(provider: str = "config", brands=None) -> Config:
    if brands is None:
        brands = [
            {
                "id": "starbucks-bogo",
                "name": "Starbucks",
                "offer": "Buy one drink get one free (BOGO)",
                "url": "https://www.starbucks.com/rewards",
                "eligibility": "Rewards members",
                "redemption": "Activate in the app",
                "verified_at": "2026-07-16",
                "locations": [
                    "102 Pike St, Seattle, WA 98101",
                    "1912 Pike Pl, Seattle, WA 98101",
                ],
            },
            {
                "id": "chipotle-freeguac",
                "name": "Chipotle",
                "offer": "Free guacamole with any entree",
                "url": "https://www.chipotle.com/",
                "locations": ["1501 Pike Pl, Seattle, WA 98101"],
            },
        ]
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["places_brand"],
        sources={"places_brand": {"provider": provider, "brands": brands}},
    )


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


# --- config provider (keyless, the default + provable-today path) ---------------

def test_config_provider_fans_offer_out_to_each_storefront():
    # 2 starbucks stores + 1 chipotle store = 3 physical RawDeals, no network.
    deals = places_brand.fetch(_config(provider="config"))

    assert len(deals) == 3
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "places_brand" for d in deals)
    # Every storefront address becomes a raw_location (-> physical -> geocoded pin).
    assert all(d.raw_location for d in deals)
    locations = {d.raw_location for d in deals}
    assert "102 Pike St, Seattle, WA 98101" in locations
    assert "1501 Pike Pl, Seattle, WA 98101" in locations
    # source_id is unique per (brand, store) so upsert never collapses two stores.
    ids = [d.source_id for d in deals]
    assert len(ids) == len(set(ids))
    # The offer text rides along as the title (classify reads it for free/BOGO).
    sbux = [d for d in deals if d.source_id.startswith("starbucks-bogo::")]
    assert len(sbux) == 2
    assert all("BOGO" in d.title for d in sbux)
    assert all(d.eligibility == "Rewards members" for d in sbux)
    assert all(d.redemption == "Activate in the app" for d in sbux)
    assert all(d.verified_at == datetime(2026, 7, 16) for d in sbux)


def test_config_provider_makes_no_network_call(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("config provider must not hit the network")

    monkeypatch.setattr(httpx, "get", boom)
    deals = places_brand.fetch(_config(provider="config"))
    assert len(deals) == 3


def test_brand_without_id_or_offer_is_skipped():
    brands = [
        {"id": "ok", "name": "Ok", "offer": "Free coffee", "locations": ["A St, Seattle"]},
        {"id": "", "name": "NoId", "offer": "Free", "locations": ["B St, Seattle"]},
        {"id": "no-offer", "name": "NoOffer", "offer": "", "locations": ["C St, Seattle"]},
    ]
    deals = places_brand.fetch(_config(provider="config", brands=brands))
    # Only the valid brand's single storefront survives.
    assert len(deals) == 1
    assert deals[0].source_id == "ok::A St, Seattle"


# --- google provider (recorded Places JSON, monkeypatched httpx) ----------------

def test_google_provider_expands_via_places_textsearch(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx, "get", fake_get)

    # One brand, no curated locations -> stores come from the fixture (3 results).
    brands = [{"id": "chipotle", "name": "Chipotle", "offer": "Free guac"}]
    deals = places_brand.fetch(_config(provider="google", brands=brands))

    assert len(deals) == 3
    assert all(d.source == "places_brand" for d in deals)
    # source_id uses Google's stable place_id, so stores never collide.
    assert all(d.source_id.startswith("chipotle::ChIJ") for d in deals)
    assert len({d.source_id for d in deals}) == 3
    # formatted_address became raw_location.
    assert all("Seattle" in d.raw_location for d in deals)
    # The API key was sent and the metro query was used.
    assert captured["params"]["key"] == "test-key"
    assert "Seattle" in captured["params"]["query"]


def test_google_provider_without_key_falls_back_to_curated(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)

    def boom(*a, **k):
        raise AssertionError("no key -> must not call Places")

    monkeypatch.setattr(httpx, "get", boom)
    # google provider but no key + curated locations present -> uses curated.
    brands = [{"id": "sb", "name": "SB", "offer": "Free", "locations": ["X St, Seattle"]}]
    deals = places_brand.fetch(_config(provider="google", brands=brands))
    assert len(deals) == 1
    assert deals[0].raw_location == "X St, Seattle"


def test_one_failing_brand_does_not_abort_others(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def fake_get(url, **kwargs):
        query = kwargs.get("params", {}).get("query", "")
        if "BadBrand" in query:
            raise httpx.ConnectError("boom")
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx, "get", fake_get)
    brands = [
        {"id": "bad", "name": "BadBrand", "offer": "Free"},
        {"id": "good", "name": "Chipotle", "offer": "Free guac"},
    ]
    deals = places_brand.fetch(_config(provider="google", brands=brands))
    # Bad brand is skipped; the good brand's 3 stores still come through.
    assert len(deals) == 3
    assert all(d.source_id.startswith("good::") for d in deals)
