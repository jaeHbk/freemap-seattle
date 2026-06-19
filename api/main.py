"""FreeMap read-only API. All business logic lives in the pipeline; this layer
only queries SQLite and shapes JSON."""

import sqlite3
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException

from scrapers.config import load_config
from scrapers.db import connect, fetch_all_deals
from scrapers.pipeline import compute_status

app = FastAPI(title="FreeMap Seattle API")

_CONFIG = load_config()


# --- Overridable dependencies (tests pin time + DB) -------------------------

def get_conn() -> sqlite3.Connection:
    """FastAPI dependency. Tests override via app.dependency_overrides."""
    return connect(_CONFIG.db_path)


def get_now() -> datetime:
    """Current wall-clock time. Tests MUST override to a fixed NOW."""
    return datetime.now()


def get_stale_after_hours() -> int:
    return load_config().stale_after_hours


# --- Helpers ----------------------------------------------------------------

def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _row_to_deal(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "source": row["source"],
        "source_id": row["source_id"],
        "dedup_key": row["dedup_key"],
        "title": row["title"],
        "url": row["url"],
        "description": row["description"],
        "deal_type": row["deal_type"],
        "category": row["category"],
        "placement": row["placement"],
        "lat": row["lat"],
        "lng": row["lng"],
        "raw_location": row["raw_location"],
        "geocode_status": row["geocode_status"],
        "posted_at": row["posted_at"],
        "expires_at": row["expires_at"],
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "alt_urls": [],
    }


def _in_bbox(deal: dict, bbox) -> bool:
    """bbox = (min_lng, min_lat, max_lng, max_lat). Deals without coords fail bbox."""
    if bbox is None:
        return True
    if deal["lat"] is None or deal["lng"] is None:
        return False
    min_lng, min_lat, max_lng, max_lat = bbox
    return (min_lng <= deal["lng"] <= max_lng) and (min_lat <= deal["lat"] <= max_lat)


def _parse_bbox(bbox: str | None):
    if not bbox:
        return None
    try:
        parts = [float(p) for p in bbox.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be 4 floats")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat")
    return tuple(parts)


def _collapse_dedup(deals: list[dict]) -> list[dict]:
    """Collapse rows sharing a dedup_key into one primary with alt_urls[].
    First-seen wins as primary; others contribute their url to alt_urls.
    Rows with no dedup_key stand alone."""
    primary_by_key: dict = {}
    result: list[dict] = []
    for d in deals:
        key = d["dedup_key"]
        if not key:
            result.append(d)
            continue
        if key not in primary_by_key:
            primary_by_key[key] = d
            result.append(d)
        else:
            prim = primary_by_key[key]
            if d["url"] not in prim["alt_urls"] and d["url"] != prim["url"]:
                prim["alt_urls"].append(d["url"])
    return result


# --- Endpoints --------------------------------------------------------------

@app.get("/api/deals")
def list_deals(
    type: str | None = None,
    category: str | None = None,
    placement: str | None = None,
    bbox: str | None = None,
    include_stale: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
    stale_after_hours: int = Depends(get_stale_after_hours),
):
    bbox_tuple = _parse_bbox(bbox)
    rows = fetch_all_deals(conn)
    out: list[dict] = []
    for row in rows:
        status = compute_status(
            _parse_dt(row["expires_at"]),
            _parse_dt(row["last_seen"]),
            now,
            stale_after_hours,
        )
        if status == "expired":
            continue
        if status == "stale" and not include_stale:
            continue
        deal = _row_to_deal(row)
        deal["status"] = status
        if type is not None and deal["deal_type"] != type:
            continue
        if category is not None and deal["category"] != category:
            continue
        if placement is not None and deal["placement"] != placement:
            continue
        if not _in_bbox(deal, bbox_tuple):
            continue
        out.append(deal)
    return _collapse_dedup(out)


@app.get("/api/deals/{deal_id}")
def deal_detail(
    deal_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
):
    row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="deal not found")
    return _row_to_deal(row)


@app.get("/api/meta")
def meta(conn: sqlite3.Connection = Depends(get_conn)):
    # Per-source deal counts from the serving table.
    count_rows = conn.execute(
        "SELECT source, COUNT(*) AS n FROM deals GROUP BY source"
    ).fetchall()
    counts = {r["source"]: r["n"] for r in count_rows}

    # Last SUCCESSFUL scrape (errors IS NULL) per source from scrape_runs.
    run_rows = conn.execute(
        "SELECT source, MAX(finished_at) AS last_ok "
        "FROM scrape_runs WHERE errors IS NULL AND finished_at IS NOT NULL "
        "GROUP BY source"
    ).fetchall()
    last_ok = {r["source"]: r["last_ok"] for r in run_rows}

    sources = sorted(set(counts) | set(last_ok))
    return {
        "sources": [
            {
                "source": s,
                "deal_count": counts.get(s, 0),
                "last_successful_scrape": last_ok.get(s),
            }
            for s in sources
        ]
    }
