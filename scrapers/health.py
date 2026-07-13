"""Post-scrape source-health check.

Reads the LATEST scrape_runs row per source and decides PASS/FAIL against the
[health] baseline in config.toml: an EXPECTED source must have a latest run that
neither errored nor found 0 deals. Sources in `minimum_pins` must also have that
many freshly geocoded rows. OPTIONAL sources are reported but never alerted;
Reddit is optional because a live runner IP can still be rate-limited.

Run as `python -m scrapers.health` (exit 0 = healthy, 1 = an expected source is
unhealthy or missing). The decision core, evaluate_health(), is pure so it's
tested without a DB.

Reuses scrapers.db.connect() (auto-Turso) and scrapers.config.load_config().
Never prints a secret — only source names, found counts, and the error text the
scraper itself stored in scrape_runs.
"""
from __future__ import annotations

import argparse
import tomllib
from datetime import datetime, timedelta

from scrapers.config import load_config
from scrapers.db import connect, init_db
from scrapers.pipeline import _as_naive_utc

# Production baseline (config.toml [health]). Used only if the [health] table is
# absent, so automation still checks the verified map-filling source.
_DEFAULT_EXPECTED = ["places_brand"]
_DEFAULT_OPTIONAL = ["reddit"]
_DEFAULT_MINIMUM_PINS = {"places_brand": 1}


def _load_health_table(config_path: str) -> dict:
    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f).get("health", {})
    except (FileNotFoundError, OSError):
        return {}


def load_health_baseline(config_path: str) -> tuple[list[str], list[str]]:
    """Read the [health] table from config.toml -> (expected, optional)."""
    health = _load_health_table(config_path)
    optional = health.get("optional")
    if optional is None:
        optional = health.get("known_dead", _DEFAULT_OPTIONAL)
    return health.get("expected", _DEFAULT_EXPECTED), optional


def load_minimum_pins(config_path: str) -> dict[str, int]:
    """Read per-source minimum fresh geocoded rows from [health]."""
    configured = _load_health_table(config_path).get(
        "minimum_pins", _DEFAULT_MINIMUM_PINS
    )
    return {
        str(source): max(0, int(minimum))
        for source, minimum in configured.items()
    }


def _is_stale(finished_at, now: datetime | None, max_age_hours: float | None) -> bool:
    """True if a run's finished_at is older than max_age_hours before now.

    Defends the false-green case: a source that didn't run THIS cycle but has a
    healthy row from a prior cycle. Missing now/window/finished_at => not stale
    (the recency check is opt-in; callers without a clock keep the old behavior).
    """
    if now is None or max_age_hours is None or not finished_at:
        return False
    fin = _as_naive_utc(finished_at if isinstance(finished_at, datetime)
                        else datetime.fromisoformat(str(finished_at)))
    now = _as_naive_utc(now)
    return fin is not None and (now - fin) > timedelta(hours=max_age_hours)


def evaluate_health(
    latest_by_source: dict[str, dict],
    expected: list[str],
    optional: list[str],
    now: datetime | None = None,
    max_age_hours: float | None = None,
    pin_counts: dict[str, int] | None = None,
    minimum_pins: dict[str, int] | None = None,
) -> dict:
    """Decide health from the latest run per source. PURE — no DB, no I/O.

    latest_by_source: {source: {"deals_found": int, "errors": str | None,
      "finished_at": str | None}}. (optional entries are ignored either way.)
    expected: sources that MUST be healthy.
    optional: sources that are reported but never alert.
    now + max_age_hours: optional recency window. When both are set, an expected
      source whose latest run finished MORE than max_age_hours ago is a problem
      ("no fresh run this cycle") — closing the stale-row false-green where a
      source that didn't run this cycle inherits a prior healthy row.

    An expected source is a problem when its latest run is MISSING, STALE,
    errored, found 0 deals, or misses its fresh-pin minimum. Returns
    {"ok": bool, "problems": [...]}.
    """
    pin_counts = pin_counts or {}
    minimum_pins = minimum_pins or {}
    problems = []
    for source in expected:
        run = latest_by_source.get(source)
        if run is None:
            problems.append(
                {"source": source, "reason": "no scrape_runs row (never ran)",
                 "deals_found": None, "errors": None}
            )
            continue
        errors = run.get("errors")
        found = run.get("deals_found")
        if _is_stale(run.get("finished_at"), now, max_age_hours):
            problems.append(
                {"source": source, "reason": f"no fresh run (last: {run.get('finished_at')})",
                 "deals_found": found, "errors": errors}
            )
        elif errors is not None:
            problems.append(
                {"source": source, "reason": "errored", "deals_found": found,
                 "errors": errors}
            )
        elif not found:  # 0 or None
            problems.append(
                {"source": source, "reason": "found 0 deals", "deals_found": found,
                 "errors": None}
            )
        elif pin_counts.get(source, 0) < minimum_pins.get(source, 0):
            pins = pin_counts.get(source, 0)
            required = minimum_pins[source]
            problems.append(
                {
                    "source": source,
                    "reason": f"found {pins} fresh map pins (minimum: {required})",
                    "deals_found": found,
                    "errors": None,
                }
            )
    return {"ok": not problems, "problems": problems}


def read_latest_runs(conn) -> dict[str, dict]:
    """Return {source: {"deals_found", "errors"}} for the most recent run per source.

    Latest = the row with the greatest id per source (scrape_runs.id is a
    monotonic AUTOINCREMENT, so it orders runs without relying on timestamp
    parsing). Bare-column MAX(id) GROUP BY would pull other columns from an
    arbitrary row in the group, so join back to the winning id explicitly.
    """
    rows = conn.execute(
        """
        SELECT s.source AS source, s.deals_found AS deals_found, s.errors AS errors,
               s.finished_at AS finished_at
        FROM scrape_runs s
        JOIN (SELECT source, MAX(id) AS mid FROM scrape_runs GROUP BY source) m
          ON s.source = m.source AND s.id = m.mid
        """
    ).fetchall()
    return {
        r["source"]: {
            "deals_found": r["deals_found"],
            "errors": r["errors"],
            "finished_at": r["finished_at"],
        }
        for r in rows
    }


def read_fresh_pin_counts(
    conn, cutoff: datetime, now: datetime
) -> dict[str, int]:
    """Count non-expired plottable rows touched during the latest cycle."""
    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS pins
        FROM deals
        WHERE placement = 'physical'
          AND geocode_status = 'ok'
          AND lat IS NOT NULL
          AND lng IS NOT NULL
          AND last_seen >= ?
          AND (expires_at IS NULL OR expires_at >= ?)
        GROUP BY source
        """,
        (cutoff.isoformat(), now.isoformat()),
    ).fetchall()
    return {r["source"]: r["pins"] for r in rows}


def format_report(
    result: dict,
    latest_by_source: dict,
    expected,
    optional,
    pin_counts: dict[str, int] | None = None,
    minimum_pins: dict[str, int] | None = None,
) -> str:
    """Human-readable per-source report. No secrets — names/counts/stored errors only.

    Drives the per-source verdict off result["problems"] so the report can never
    disagree with evaluate_health's decision (incl. the staleness check)."""
    pin_counts = pin_counts or {}
    minimum_pins = minimum_pins or {}
    problem_by_source = {p["source"]: p for p in result["problems"]}
    lines = ["FreeMap health check:"]
    for source in expected:
        prob = problem_by_source.get(source)
        run = latest_by_source.get(source)
        if prob is not None:
            lines.append(f"  [FAIL] {source}: {prob['reason']}")
        else:
            pin_detail = (
                f" pins={pin_counts.get(source, 0)}"
                if source in minimum_pins
                else ""
            )
            lines.append(
                f"  [ok]   {source}: found={run['deals_found']}{pin_detail}"
            )
    for source in optional:
        run = latest_by_source.get(source)
        detail = "no row" if run is None else f"found={run.get('deals_found')}"
        lines.append(f"  [opt]  {source}: {detail} (optional, not alerting)")
    lines.append("HEALTHY" if result["ok"] else "UNHEALTHY")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="scrapers.health",
        description="Check the latest scrape_runs per source against the [health] baseline.",
    )
    parser.add_argument("--db", default=None, help="DB path (overrides config.db_path).")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml.")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=None,
        help="Flag an expected source whose latest run is older than this as 'no fresh "
             "run' (default: 2x the freshness window from config, so a source that "
             "skips a cycle is caught). Pass 0 to disable the recency check.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    expected, optional = load_health_baseline(args.config)
    minimum_pins = load_minimum_pins(args.config)

    # A source scrapes ~every cycle; allow ~2 freshness windows before alarming on
    # staleness (24h default -> 48h), so one delayed/missed run doesn't false-alert
    # but a source that silently stopped recording IS caught. 0 disables.
    max_age = args.max_age_hours if args.max_age_hours is not None else config.stale_after_hours * 2
    max_age = max_age or None  # 0 -> None (disabled)

    db_path = args.db if args.db is not None else config.db_path
    conn = connect(db_path)
    init_db(conn)  # idempotent; ensures scrape_runs exists for an empty/new DB
    try:
        latest = read_latest_runs(conn)
        # The workflow timeout is 20 minutes. One hour includes this cycle while
        # excluding the previous run from the 12-hour schedule.
        pin_now = datetime.now()
        pin_counts = read_fresh_pin_counts(
            conn, pin_now - timedelta(hours=1), pin_now
        )
    finally:
        conn.close()

    result = evaluate_health(
        latest,
        expected,
        optional,
        now=datetime.now(),
        max_age_hours=max_age,
        pin_counts=pin_counts,
        minimum_pins=minimum_pins,
    )
    print(
        format_report(
            result, latest, expected, optional, pin_counts, minimum_pins
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
