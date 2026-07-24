"""Candidate evidence and publication policy.

Discovery is intentionally broad. Publication is deliberately narrower: every
claim is staged, but only claims with current official evidence or independent
corroboration can reach the user-facing deals table.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from scrapers.contract import Deal, RawDeal

OFFICIAL_VERIFICATION_MAX_AGE_DAYS = 30

SOURCE_TIERS = {
    "places_brand": "official",
    "chains": "official",
    "reddit": "community",
    "local": "editorial",
    "slickdeals": "aggregator",
}

EVIDENCE_TYPES = {
    "official": "official_terms",
    "community": "community_post",
    "editorial": "editorial_listing",
    "aggregator": "aggregator_listing",
}


@dataclass(frozen=True)
class PublicationDecision:
    decision: str
    reason: str
    quality_score: int
    verification_status: str | None


def source_tier(source: str) -> str:
    """Classify a source conservatively when it is not in the registry."""
    return SOURCE_TIERS.get(source, "aggregator")


def evidence_type(tier: str) -> str:
    return EVIDENCE_TYPES.get(tier, "aggregator_listing")


def evidence_excerpt(raw: RawDeal) -> str:
    """Return a compact human-readable observation without storing raw payloads."""
    parts = [raw.title]
    if raw.description:
        parts.append(raw.description)
    return " | ".join(parts)[:500]


def evidence_hash(raw: RawDeal) -> str:
    """Fingerprint the meaningful claim fields so unchanged evidence deduplicates."""
    payload = {
        "source": raw.source,
        "source_id": raw.source_id,
        "title": raw.title,
        "url": raw.url,
        "description": raw.description,
        "eligibility": raw.eligibility,
        "redemption": raw.redemption,
        "verified_at": _iso(raw.verified_at),
        "raw_location": raw.raw_location,
        "posted_at": _iso(raw.posted_at),
        "expires_at": _iso(raw.expires_at),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_candidate(
    deal: Deal,
    *,
    tier: str,
    now: datetime,
    independent_source_count: int,
) -> PublicationDecision:
    """Apply hard scope gates followed by evidence and location requirements."""
    valid_url = _valid_http_url(deal.url)
    current = not _expired(deal.expires_at, now)
    location_ready = (
        deal.placement == "online"
        or (
            deal.geocode_status == "ok"
            and deal.lat is not None
            and deal.lng is not None
        )
    )
    structured_terms = bool(deal.eligibility and deal.redemption)

    score = 0
    if deal.deal_type in {"free", "bogo"}:
        score += 40
    if valid_url:
        score += 10
    if current:
        score += 10
    if structured_terms:
        score += 5
    if location_ready:
        score += 5

    if deal.deal_type not in {"free", "bogo"}:
        return PublicationDecision("rejected", "out_of_scope", score, None)
    if not valid_url:
        return PublicationDecision("rejected", "invalid_source_url", score, None)
    if not current:
        return PublicationDecision("rejected", "expired", score, None)

    if tier == "official":
        verification_reason = _official_verification_problem(deal.verified_at, now)
        if verification_reason is not None:
            return PublicationDecision("pending", verification_reason, score, None)
        score += 30
        if not location_ready:
            return PublicationDecision("pending", "location_unresolved", score, None)
        return PublicationDecision(
            "accepted",
            "current_official_evidence",
            score,
            "official",
        )

    if not location_ready:
        return PublicationDecision("pending", "location_unresolved", score, None)
    if independent_source_count >= 2:
        score += 30
        return PublicationDecision(
            "accepted",
            "independently_corroborated",
            score,
            "corroborated",
        )
    return PublicationDecision(
        "pending",
        "independent_corroboration_required",
        score,
        None,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except (TypeError, ValueError):
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _expired(expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return False
    return _naive_utc(expires_at) < _naive_utc(now)


def _official_verification_problem(
    verified_at: datetime | None,
    now: datetime,
) -> str | None:
    if verified_at is None:
        return "official_verification_required"
    verified = _naive_utc(verified_at)
    current = _naive_utc(now)
    if verified > current:
        return "official_verification_invalid"
    if (
        current.date() - verified.date()
    ).days > OFFICIAL_VERIFICATION_MAX_AGE_DAYS:
        return "official_verification_stale"
    return None
