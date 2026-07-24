from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawDeal:
    source: str
    source_id: str
    title: str
    url: str
    description: str | None = None
    eligibility: str | None = None
    redemption: str | None = None
    verified_at: datetime | None = None
    raw_location: str | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Deal:
    source: str
    source_id: str
    title: str
    url: str
    description: str | None
    deal_type: str        # "free" | "bogo" | "other"
    category: str         # "food" | "retail" | "event" | "other"
    placement: str        # "physical" | "online"
    lat: float | None
    lng: float | None
    raw_location: str | None
    geocode_status: str   # "ok" | "failed" | "n/a" | "pending"
    posted_at: datetime | None
    expires_at: datetime | None
    dedup_key: str | None = None
    eligibility: str | None = None
    redemption: str | None = None
    verified_at: datetime | None = None
    candidate_id: int | None = None
    source_tier: str | None = None
    verification_status: str | None = None
    evidence_count: int | None = None
    quality_score: int | None = None
    publication_reason: str | None = None
