import hashlib
from datetime import datetime, timedelta, timezone

from scrapers.contract import RawDeal, Deal
from scrapers.deal_scope import classify_deal_type
from scrapers.db import (
    candidate_evidence_stats,
    unpublish_deal,
    update_candidate_decision,
    upsert_candidate,
    upsert_deals,
    upsert_evidence,
)
from scrapers.publication import (
    evaluate_candidate,
    evidence_excerpt,
    evidence_hash,
    evidence_type,
    source_tier,
)


def normalize(raw: RawDeal) -> RawDeal:
    """Strip/collapse whitespace in title/description; defensive date pass.

    Never raises: a bad/non-datetime date becomes None.
    """
    def _clean(s: str | None) -> str | None:
        if s is None:
            return None
        return " ".join(s.split())

    def _safe_dt(v: object) -> datetime | None:
        return v if isinstance(v, datetime) else None

    raw.title = _clean(raw.title) or ""
    raw.description = _clean(raw.description)
    raw.eligibility = _clean(raw.eligibility)
    raw.redemption = _clean(raw.redemption)
    raw.verified_at = _safe_dt(raw.verified_at)
    raw.raw_location = _clean(raw.raw_location)
    raw.posted_at = _safe_dt(raw.posted_at)
    raw.expires_at = _safe_dt(raw.expires_at)
    return raw


def classify(raw: RawDeal) -> Deal:
    """Derive deal_type, placement, category from a (normalized) RawDeal.

    Ambiguous inputs fall back to safe defaults ("other"/"online").
    lat=lng=None always; geocode_status is "n/a" for online, "pending" for physical.
    """
    text = " ".join(p for p in (raw.title, raw.description) if p).lower()

    deal_type = classify_deal_type(raw.title, raw.description)

    placement = "physical" if raw.raw_location else "online"

    if any(k in text for k in ("food", "coffee", "burrito", "pizza", "drink", "meal")):
        category = "food"
    elif any(
        k in text
        for k in (
            "event",
            "show",
            "concert",
            "festival",
            "museum",
            "gallery",
            "admission",
        )
    ):
        category = "event"
    elif any(
        k in text
        for k in ("store", "retail", "clothing", "shoes", "beauty", "cosmetic")
    ):
        category = "retail"
    else:
        category = "other"

    geocode_status = "pending" if placement == "physical" else "n/a"

    return Deal(
        source=raw.source,
        source_id=raw.source_id,
        title=raw.title,
        url=raw.url,
        description=raw.description,
        eligibility=raw.eligibility,
        redemption=raw.redemption,
        verified_at=raw.verified_at,
        deal_type=deal_type,
        category=category,
        placement=placement,
        lat=None,
        lng=None,
        raw_location=raw.raw_location,
        geocode_status=geocode_status,
        posted_at=raw.posted_at,
        expires_at=raw.expires_at,
    )


def geocode_deal(deal: Deal, geocoder) -> Deal:
    """Resolve a physical deal's raw_location to lat/lng via the geocoder.

    Only acts when placement=="physical" and geocode_status=="pending".
    On hit -> set lat/lng + status "ok"; on miss -> leave NULL + status "failed".
    Online / already-resolved deals pass through unchanged.
    """
    if deal.placement == "physical" and deal.geocode_status == "pending":
        try:
            result = geocoder.geocode(deal.raw_location) if deal.raw_location else None
        except Exception:
            # A geocoder error (e.g. provider 403/timeout) must DEMOTE the deal to
            # failed-geocode (it still surfaces in the list view), never let the
            # exception escape — run_pipeline's per-row except would otherwise drop
            # the whole deal silently. Demote, don't disappear.
            result = None
        if result is not None:
            deal.lat, deal.lng = result
            deal.geocode_status = "ok"
        else:
            deal.lat = None
            deal.lng = None
            deal.geocode_status = "failed"
    return deal


def dedup(deals: list[Deal]) -> list[Deal]:
    """Set .dedup_key on each deal (normalized hash of title+location+deal_type).

    Does NOT remove rows; the API collapses dedup_key groups on read.
    """
    def _norm(s: str | None) -> str:
        return " ".join(s.split()).lower() if s else ""

    for deal in deals:
        basis = "|".join((_norm(deal.title), _norm(deal.raw_location), deal.deal_type))
        deal.dedup_key = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return deals


def _as_naive_utc(dt: datetime | None) -> datetime | None:
    """Coerce a datetime to naive-UTC; pass None/naive values through unchanged.

    The project standardizes on naive-UTC internally. Upstream sources can yield
    timezone-AWARE datetimes (e.g. a chain offers page <time datetime="...-07:00">
    parsed via datetime.fromisoformat), and comparing aware vs naive raises
    TypeError. Converting any aware value to UTC and dropping tzinfo here makes the
    downstream comparisons total so a single aware row can never 500 the API.
    """
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def compute_status(expires_at, last_seen, now, stale_after_hours: int) -> str:
    """Pure freshness function.

    "expired" if expires_at is set and in the past;
    else "stale" if (now - last_seen) > stale_after_hours hours;
    else "active".

    Inputs are coerced to naive-UTC (the internal standard) so the comparison is
    total and never raises on a mixed aware/naive pair.
    """
    expires_at = _as_naive_utc(expires_at)
    last_seen = _as_naive_utc(last_seen)
    now = _as_naive_utc(now)
    if expires_at is not None and expires_at < now:
        return "expired"
    if last_seen is not None and (now - last_seen) > timedelta(hours=stale_after_hours):
        return "stale"
    return "active"


def run_pipeline(raws: list[RawDeal], geocoder, conn, now) -> int:
    """Stage every valid raw observation, then publish only accepted candidates.

    One malformed row never aborts the batch. Out-of-scope rows are retained as
    rejected candidates but skip geocoding. Returns the number of published rows
    upserted, preserving the function's existing caller contract.
    """
    normalized_pairs: list[tuple[RawDeal, Deal]] = []
    for raw in raws:
        try:
            normalized = normalize(raw)
            deal = classify(normalized)
            if deal.deal_type in {"free", "bogo"}:
                deal = geocode_deal(deal, geocoder)
            normalized_pairs.append((normalized, deal))
        except Exception:
            # One malformed raw must not abort the batch.
            continue

    dedup([deal for _, deal in normalized_pairs])
    staged: list[tuple[RawDeal, Deal, int, str]] = []
    for raw, deal in normalized_pairs:
        candidate_id: int | None = None
        try:
            tier = source_tier(deal.source)
            candidate_id = upsert_candidate(
                conn,
                deal,
                now,
                source_tier=tier,
            )
            upsert_evidence(
                conn,
                candidate_id=candidate_id,
                source=raw.source,
                source_id=raw.source_id,
                evidence_type=evidence_type(tier),
                url=raw.url,
                excerpt=evidence_excerpt(raw),
                content_hash=evidence_hash(raw),
                observed_at=now,
            )
            staged.append((raw, deal, candidate_id, tier))
        except Exception:
            try:
                if candidate_id is not None:
                    update_candidate_decision(
                        conn,
                        candidate_id,
                        decision="pending",
                        reason="evidence_processing_failed",
                        quality_score=0,
                    )
                unpublish_deal(conn, deal.source, deal.source_id)
            except Exception:
                pass
            continue

    published: list[Deal] = []
    for _, deal, candidate_id, tier in staged:
        try:
            stats = candidate_evidence_stats(conn, deal.dedup_key)
            decision = evaluate_candidate(
                deal,
                tier=tier,
                now=now,
                independent_source_count=stats["source_count"],
            )
            update_candidate_decision(
                conn,
                candidate_id,
                decision=decision.decision,
                reason=decision.reason,
                quality_score=decision.quality_score,
            )
            if decision.decision == "accepted":
                deal.candidate_id = candidate_id
                deal.source_tier = tier
                deal.verification_status = decision.verification_status
                deal.evidence_count = stats["evidence_count"]
                deal.quality_score = decision.quality_score
                deal.publication_reason = decision.reason
                published.append(deal)
            else:
                unpublish_deal(conn, deal.source, deal.source_id)
        except Exception:
            try:
                update_candidate_decision(
                    conn,
                    candidate_id,
                    decision="pending",
                    reason="publication_evaluation_failed",
                    quality_score=0,
                )
                unpublish_deal(conn, deal.source, deal.source_id)
            except Exception:
                pass
            continue

    conn.commit()
    return upsert_deals(conn, published, now)
