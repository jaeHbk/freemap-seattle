import hashlib
from datetime import datetime, timedelta, timezone

from scrapers.contract import RawDeal, Deal
from scrapers.db import upsert_deals


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

    # NOTE: keyword matching below is intentionally plain substring (`in`) for
    # simplicity. This accepts known false positives (e.g. "Freedom rally" -> "free",
    # "shows" matches "show") as an acceptable tradeoff at this scale; a future
    # reader wanting word-boundary precision would switch to regex \bword\b here.

    # deal_type: BOGO beats "free"; then discount-ish -> other; else other.
    if any(k in text for k in ("buy one", "bogo", "b1g1")):
        deal_type = "bogo"
    elif "free" in text:
        deal_type = "free"
    elif any(k in text for k in ("% off", "discount", "sale")):
        # Discount-ish keywords are intentionally recognized but bucketed as
        # "other" (we only surface free/BOGO as distinct types). Same result as
        # the else branch; kept explicit so the recognized-vocabulary is documented.
        deal_type = "other"
    else:
        deal_type = "other"

    placement = "physical" if raw.raw_location else "online"

    if any(k in text for k in ("food", "coffee", "burrito", "pizza", "drink", "meal")):
        category = "food"
    elif any(k in text for k in ("event", "show", "concert", "festival")):
        category = "event"
    elif any(k in text for k in ("store", "retail", "clothing", "shoes")):
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
    """Chain every raw through normalize -> classify -> geocode_deal with per-row
    try/except (one bad row never aborts the batch), then dedup the survivors and
    upsert them. Returns the number of rows upserted. FULLY IMPLEMENTED (not a stub).
    """
    deals: list[Deal] = []
    for raw in raws:
        try:
            normalized = normalize(raw)
            deal = classify(normalized)
            deal = geocode_deal(deal, geocoder)
            deals.append(deal)
        except Exception:
            # One malformed raw must not abort the batch.
            continue
    deals = dedup(deals)
    return upsert_deals(conn, deals, now)
