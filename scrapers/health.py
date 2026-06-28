"""Post-scrape source-health check.

Reads the LATEST scrape_runs row per source and decides PASS/FAIL against the
[health] baseline in config.toml: an EXPECTED source must have a latest run that
neither errored nor found 0 deals. KNOWN-DEAD sources (reddit, chains — 403 /
synthetic host, 0 forever) are never alerted: the normal "2 of N dead" steady
state must not page.

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

# Plan baseline (config.toml [health]). Used only if the [health] table is
# absent from the config file, so an old config still checks the right sources.
_DEFAULT_EXPECTED = ["places_brand", "slickdeals", "local"]
_DEFAULT_KNOWN_DEAD = ["reddit", "chains"]


def load_health_baseline(config_path: str) -> tuple[list[str], list[str]]:
    """Read the [health] table from config.toml -> (expected, known_dead).

    Parsed here (not via scrapers.config.Config) so the health lane owns its own
    config surface; falls back to the plan defaults if the table is missing.
    """
    try:
        with open(config_path, "rb") as f:
            health = tomllib.load(f).get("health", {})
    except (FileNotFoundError, OSError):
        health = {}
    return (
        health.get("expected", _DEFAULT_EXPECTED),
        health.get("known_dead", _DEFAULT_KNOWN_DEAD),
    )


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
    known_dead: list[str],
    now: datetime | None = None,
    max_age_hours: float | None = None,
) -> dict:
    """Decide health from the latest run per source. PURE — no DB, no I/O.

    latest_by_source: {source: {"deals_found": int, "errors": str | None,
      "finished_at": str | None}}. (known_dead entries are ignored either way.)
    expected: sources that MUST be healthy.
    known_dead: sources that are allowed to be dead and never alert.
    now + max_age_hours: optional recency window. When both are set, an expected
      source whose latest run finished MORE than max_age_hours ago is a problem
      ("no fresh run this cycle") — closing the stale-row false-green where a
      source that didn't run this cycle inherits a prior healthy row.

    An expected source is a problem when its latest run is MISSING, STALE, errored,
    or found 0 deals. Returns {"ok": bool, "problems": [...]}.
    """
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


def format_report(result: dict, latest_by_source: dict, expected, known_dead) -> str:
    """Human-readable per-source report. No secrets — names/counts/stored errors only.

    Drives the per-source verdict off result["problems"] so the report can never
    disagree with evaluate_health's decision (incl. the staleness check)."""
    problem_by_source = {p["source"]: p for p in result["problems"]}
    lines = ["FreeMap health check:"]
    for source in expected:
        prob = problem_by_source.get(source)
        run = latest_by_source.get(source)
        if prob is not None:
            lines.append(f"  [FAIL] {source}: {prob['reason']}")
        else:
            lines.append(f"  [ok]   {source}: found={run['deals_found']}")
    for source in known_dead:
        run = latest_by_source.get(source)
        detail = "no row" if run is None else f"found={run.get('deals_found')}"
        lines.append(f"  [dead] {source}: {detail} (known-dead, not alerting)")
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
    expected, known_dead = load_health_baseline(args.config)

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
    finally:
        conn.close()

    result = evaluate_health(latest, expected, known_dead, now=datetime.now(), max_age_hours=max_age)
    print(format_report(result, latest, expected, known_dead))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
