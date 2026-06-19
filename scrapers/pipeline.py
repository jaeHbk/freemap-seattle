from datetime import datetime

from scrapers.contract import RawDeal, Deal


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
    """Derive deal_type, placement, category; lat=lng=None;
    geocode_status="n/a" if online else "pending".

    STUB — implemented test-first in Milestone 2.
    """
    raise NotImplementedError("classify is implemented in Milestone 2")


def geocode_deal(deal: Deal, geocoder) -> Deal:
    """If placement=="physical" and geocode_status=="pending":
    geocoder.geocode(raw_location) -> set lat/lng + status "ok"/"failed";
    else unchanged.

    STUB — implemented test-first in Milestone 2.
    """
    raise NotImplementedError("geocode_deal is implemented in Milestone 2")


def dedup(deals: list[Deal]) -> list[Deal]:
    """Set .dedup_key on each (normalized hash of merchant/title + location +
    deal_type); does NOT remove rows (API collapses on read).

    STUB — implemented test-first in Milestone 2.
    """
    raise NotImplementedError("dedup is implemented in Milestone 2")


def compute_status(expires_at, last_seen, now, stale_after_hours: int) -> str:
    """Pure function -> "expired" | "stale" | "active".

    expired if expires_at and expires_at < now;
    stale if (now - last_seen) > stale_after_hours hours; else active.

    STUB — implemented test-first in Milestone 2.
    """
    raise NotImplementedError("compute_status is implemented in Milestone 2")


def run_pipeline(raws: list[RawDeal], geocoder, conn, now) -> int:
    """For each raw: try/except (one bad row never aborts the batch) ->
    normalize -> classify -> geocode_deal; collect; dedup; upsert_deals; return count.

    STUB ONLY — FULLY IMPLEMENTED (NOT a stub) in Milestone 2. Present now so the
    package imports cleanly. Must NOT remain NotImplementedError after Milestone 2.
    """
    raise NotImplementedError("run_pipeline is implemented in Milestone 2")
