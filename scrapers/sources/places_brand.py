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
    provider = "config"             # "config" (keyless) | "google"
    metro_query = "Seattle, WA"     # bias for Places text search
    verification_max_age_days = 30  # fail closed when terms need review

    [[sources.places_brand.brands]]
    id = "chipotle-rewards"
    name = "Chipotle"
    offer = "Free chips and guacamole with a meal purchase for new Rewards members"
    url = "https://www.chipotle.com/rewards"
    verified_at = "2026-07-17"
    expires_at = "2026-12-31"  # optional; date-only values include the full day
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
from datetime import date, datetime, time, timedelta, timezone

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal

PLACES_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


class VerificationError(RuntimeError):
    """Configured official terms are missing, stale, invalid, or expired."""


def _timestamp(value: object, *, end_of_day: bool = False) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if end_of_day and len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.max)
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _verification_terms(
    brands: list[dict],
    max_age_days: int | None,
    now: datetime,
) -> list[tuple[datetime | None, datetime | None]]:
    """Validate official terms before refreshing any storefront rows."""
    now = _naive_utc(now)
    terms: list[tuple[datetime | None, datetime | None]] = []
    problems: list[str] = []

    for brand in brands:
        brand_id = (brand.get("id") or "").strip()
        offer = (brand.get("offer") or "").strip()
        verified_at = _timestamp(brand.get("verified_at"))
        expires_raw = brand.get("expires_at")
        expires_at = _timestamp(expires_raw, end_of_day=True)
        terms.append((verified_at, expires_at))

        # Existing malformed-brand isolation remains intact.
        if not brand_id or not offer:
            continue

        label = (brand.get("name") or brand_id).strip()
        if max_age_days is not None:
            if verified_at is None:
                problems.append(f"{label}: verified_at is required and must be ISO-8601")
            else:
                verified = _naive_utc(verified_at)
                age_days = (now.date() - verified.date()).days
                if age_days < 0:
                    problems.append(f"{label}: verified_at is in the future")
                elif age_days > max_age_days:
                    due = verified.date() + timedelta(days=max_age_days)
                    problems.append(f"{label}: verification overdue since {due.isoformat()}")

        if expires_raw not in (None, "") and expires_at is None:
            problems.append(f"{label}: expires_at must be ISO-8601")
        elif expires_at is not None and _naive_utc(expires_at) < now:
            problems.append(f"{label}: offer expired at {expires_at.isoformat()}")

    if problems:
        raise VerificationError(
            "places_brand verification failed: " + "; ".join(problems)
        )
    return terms


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


def fetch(config: Config, now: datetime | None = None) -> list[RawDeal]:
    settings = config.sources.get("places_brand", {})
    provider = settings.get("provider", "config")
    metro_query = settings.get("metro_query", "Seattle, WA")
    brands: list[dict] = settings.get("brands", [])
    max_age_raw = settings.get("verification_max_age_days")
    if max_age_raw is None:
        max_age_days = None
    else:
        if isinstance(max_age_raw, bool) or not isinstance(max_age_raw, int):
            raise VerificationError(
                "places_brand verification_max_age_days must be a positive integer"
            )
        max_age_days = max_age_raw
        if max_age_days <= 0:
            raise VerificationError(
                "places_brand verification_max_age_days must be a positive integer"
            )

    terms = _verification_terms(brands, max_age_days, now or datetime.now())

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY") if provider == "google" else None

    deals: list[RawDeal] = []
    for brand, (verified_at, expires_at) in zip(brands, terms, strict=True):
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
                        expires_at=expires_at,
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
