"""places_brand source: expand a brand's current free/BOGO offer into one PHYSICAL
RawDeal per Seattle storefront, so a single chain-wide promo becomes many map pins.

This generalizes chains.py's offer x branch fan-out: instead of a hardcoded
branch-address table per chain, storefront locations come from either curated config
(provider="config", keyless — provable today) or the Google Places API
(provider="google", needs GOOGLE_MAPS_API_KEY). Either way each storefront yields a
RawDeal with raw_location set, which the unchanged pipeline classifies physical and
the geocoder resolves to lat/lng.

Config shape (config.toml):

    [sources.places_brand]
    provider = "config"          # "config" (keyless) | "google"
    metro_query = "Seattle, WA"  # bias for Places text search

    [[sources.places_brand.brands]]
    id = "chipotle-rewards"
    name = "Chipotle"
    offer = "Free chips and guacamole with a meal purchase for new Rewards members"
    url = "https://www.chipotle.com/rewards"
    # provider="config": curated real storefront addresses ->
    locations = [
      "1501 4th Ave, Seattle, WA 98101",
      "4229 University Way NE, Seattle, WA 98105",
    ]
    # provider="google": omit `locations`; storefronts are discovered via Places.

Offer text is what classify() reads for deal_type/category, so phrase it with the
free/BOGO + food/retail keywords (pipeline.py classify)."""

from __future__ import annotations

import os
from datetime import datetime

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal

PLACES_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


def _verified_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def _storefronts_from_config(brand: dict) -> list[tuple[str, str]]:
    """Curated keyless path: (place_key, address) per configured location.

    place_key is the address itself — stable and unique per storefront, which is
    all the composite source_id needs.
    """
    out: list[tuple[str, str]] = []
    for addr in brand.get("locations", []):
        addr = (addr or "").strip()
        if addr:
            out.append((addr, addr))
    return out


def _storefronts_from_google(brand: dict, metro_query: str, api_key: str) -> list[tuple[str, str]]:
    """Discover storefronts via Places Text Search, biased to the metro.

    Returns (place_id, formatted_address). place_id is Google's stable per-store
    key, so the composite source_id never collides across stores. One live call per
    brand; a failure raises and the caller's per-brand try/except skips that brand.
    """
    query = f"{brand['name']} {metro_query}".strip()
    resp = httpx.get(
        PLACES_TEXTSEARCH_URL,
        params={"query": query, "key": api_key},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        # A real API error (REQUEST_DENIED, OVER_QUERY_LIMIT, ...) should not be
        # silently treated as "no stores" — raise so this brand is recorded skipped.
        raise RuntimeError(f"Places textsearch status={data.get('status')}")
    out: list[tuple[str, str]] = []
    for r in data.get("results", []):
        place_id = (r.get("place_id") or "").strip()
        addr = (r.get("formatted_address") or "").strip()
        if place_id and addr:
            out.append((place_id, addr))
    return out


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("places_brand", {})
    provider = settings.get("provider", "config")
    metro_query = settings.get("metro_query", "Seattle, WA")
    brands: list[dict] = settings.get("brands", [])

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY") if provider == "google" else None

    deals: list[RawDeal] = []
    for brand in brands:
        # Per-brand isolation mirrors chains.py: one brand failing (bad config, a
        # Places error) is skipped, never fatal to the whole fetch.
        try:
            brand_id = (brand.get("id") or "").strip()
            name = (brand.get("name") or "").strip()
            offer = (brand.get("offer") or "").strip()
            # An offer with no stable id or no offer text would produce colliding
            # "::<store>" ids or an untitled deal; skip it (chains.py guard).
            if not brand_id or not offer:
                continue
            offer_url = (brand.get("url") or "").strip() or ""
            eligibility = (brand.get("eligibility") or "").strip() or None
            redemption = (brand.get("redemption") or "").strip() or None
            verified_at = _verified_at(brand.get("verified_at"))

            if provider == "google" and api_key:
                storefronts = _storefronts_from_google(brand, metro_query, api_key)
            else:
                # "config" provider, or "google" with no key -> curated addresses.
                storefronts = _storefronts_from_config(brand)

            for place_key, address in storefronts:
                # Composite id keeps each storefront a distinct upsert row.
                source_id = f"{brand_id}::{place_key}"
                deals.append(
                    RawDeal(
                        source="places_brand",
                        source_id=source_id,
                        title=offer,
                        url=offer_url or f"https://www.google.com/maps/search/{name}",
                        description=f"{name} — {address}",
                        eligibility=eligibility,
                        redemption=redemption,
                        verified_at=verified_at,
                        raw_location=address,
                        posted_at=None,
                        expires_at=None,
                        raw={
                            "brand_id": brand_id,
                            "brand": name,
                            "place_key": place_key,
                            "provider": provider,
                        },
                    )
                )
        except Exception:
            # One bad brand is skipped, not fatal.
            continue
    return deals
