"""Pluggable geocoders, all behind the same `.geocode(raw_location)->(lat,lng)|None`
duck type the pipeline already calls (pipeline.py geocode_deal).

The base Geocoder (Nominatim, cache-first, rate-limited) lives in geocode.py and
stays the keyless default. GoogleGeocoder here overrides ONLY the single live HTTP
call, inheriting the geocode_cache + rate-limit/cap machinery wholesale.

`make_geocoder(provider, conn, config)` picks the implementation by config; an
unknown provider or a missing key falls back to Nominatim so a scrape never breaks
just because no key is set."""

from __future__ import annotations

import os

import httpx

from scrapers.geocode import Geocoder

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
CENSUS_GEOCODE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


class CensusGeocoder(Geocoder):
    """Geocoder backed by the US Census Bureau geocoder — official, KEYLESS, and
    (unlike the public Nominatim endpoint, which now policy-blocks server traffic)
    usable for unattended scrapes. US addresses only, which fits a Seattle metro.

    Reuses Geocoder's cache + rate-limit/cap; only the live call differs.
    """

    def _live_geocode(self, raw_location: str) -> tuple[float, float] | None:
        resp = httpx.get(
            CENSUS_GEOCODE_URL,
            params={
                "address": raw_location,
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        c = matches[0]["coordinates"]  # x=lng, y=lat
        return (float(c["y"]), float(c["x"]))


class GoogleGeocoder(Geocoder):
    """Geocoder backed by the Google Maps Geocoding API.

    Reuses Geocoder's cache-first lookup, per-run live-call cap, and polite
    rate limit; only the live call differs (and it needs an API key).
    """

    def __init__(self, conn, api_key: str, **kwargs):
        super().__init__(conn, **kwargs)
        self.api_key = api_key

    def _live_geocode(self, raw_location: str) -> tuple[float, float] | None:
        resp = httpx.get(
            GOOGLE_GEOCODE_URL,
            params={"address": raw_location, "key": self.api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # status "ZERO_RESULTS" (or any non-OK) -> treat as a miss, which the
        # caller caches as "failed" so we never re-hit it.
        if data.get("status") != "OK" or not data.get("results"):
            return None
        loc = data["results"][0]["geometry"]["location"]
        return (float(loc["lat"]), float(loc["lng"]))


def make_geocoder(provider: str, conn, config) -> Geocoder:
    """Build the geocoder named by `provider`, reusing config's rate-limit knobs.

    - "census"   : US Census geocoder — keyless, the DEFAULT (works unattended).
    - "google"   : Google Maps Geocoding — needs GOOGLE_MAPS_API_KEY in env.
    - "nominatim": OSM Nominatim — keyless but its public endpoint now 403s server
                   traffic, so it's kept only for local/dev use, not the default.

    provider="google" without a key, or any unknown provider, falls back to the
    keyless Census geocoder so a scrape is never blocked on a missing secret. Keys
    come from env ONLY, never config/commit.
    """
    common = dict(
        user_agent=config.user_agent,
        min_interval_seconds=config.geocoder_min_interval_seconds,
        max_live_calls=config.geocoder_max_live_calls,
    )
    if provider == "google":
        key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if key:
            return GoogleGeocoder(conn, api_key=key, **common)
        # No key -> degrade to the keyless Census geocoder rather than fail.
    if provider == "nominatim":
        return Geocoder(conn, **common)
    # "census" and any unknown provider -> keyless Census default.
    return CensusGeocoder(conn, **common)
