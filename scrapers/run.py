"""Orchestrate all sources through the pipeline and record scrape_runs.

Single unattended entrypoint (`python -m scrapers.run`) with zero secrets —
suitable for `meshclaw run TASK.md` on cron. One source failing never aborts
the others; every source's outcome is recorded in scrape_runs.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime

from scrapers.config import Config, load_config
from scrapers.contract import RawDeal
from scrapers.db import connect, init_db, record_run
from scrapers.geocoders import make_geocoder
from scrapers.pipeline import run_pipeline
from scrapers.sources import reddit, chains, slickdeals, local, places_brand

# Module-level registry: source name -> fetch callable.
# Milestone 3 wires only reddit; Milestone 5 adds chains/slickdeals/local;
# Milestone 6 adds the main() CLI entrypoint (which imports connect/init_db/
# load_config/Geocoder). Keep this registry the single source of truth.
SOURCES: dict[str, Callable[..., list[RawDeal]]] = {
    "reddit": reddit.fetch,
    "chains": chains.fetch,
    "slickdeals": slickdeals.fetch,
    "local": local.fetch,
    "places_brand": places_brand.fetch,
}


def run_all(
    config: Config,
    conn,
    geocoder,
    now: datetime,
    sources: dict | None = None,
) -> dict[str, dict]:
    """Run each source's fetch -> pipeline, recording every outcome.

    `sources` defaults to the enabled subset of the SOURCES registry; tests
    inject a custom dict. For each source the fetch + run_pipeline are wrapped
    in try/except so one failing source never aborts the others.

    Returns {source_name: {"deals_found": int, "upserted": int,
                           "errors": str | None}}.
    """
    if sources is None:
        sources = {name: SOURCES[name] for name in config.sources_enabled}

    summary: dict[str, dict] = {}
    for name, fetch in sources.items():
        # scrape_runs timestamps are wall-clock so finished - started is a real
        # duration. The injected `now` stays the pipeline's *logical* clock
        # (freshness/last_seen); mixing it into started_at produced garbage
        # durations (e.g. started=2020 / finished=2026).
        started_at = datetime.now()
        try:
            raws = fetch(config)
            deals_found = len(raws)
            upserted = run_pipeline(raws, geocoder, conn, now)
            finished_at = datetime.now()
            record_run(conn, name, started_at, finished_at, deals_found, None)
            summary[name] = {
                "deals_found": deals_found,
                "upserted": upserted,
                "errors": None,
            }
        except Exception as e:  # noqa: BLE001 - isolate one source's failure
            finished_at = datetime.now()
            record_run(conn, name, started_at, finished_at, 0, str(e))
            summary[name] = {
                "deals_found": 0,
                "upserted": 0,
                "errors": str(e),
            }
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="scrapers.run",
        description="FreeMap scrape entrypoint: run all enabled sources through the pipeline into SQLite.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to the SQLite DB (overrides config.db_path).",
    )
    parser.add_argument(
        "--config",
        default="config.toml",
        help="Path to config.toml (default: config.toml).",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, OSError):
        print(f"config not found: {args.config}", file=sys.stderr)
        return 1

    db_path = args.db if args.db is not None else config.db_path

    conn = connect(db_path)
    init_db(conn)

    try:
        # Geocoder provider is config-driven (keyless Nominatim by default; "google"
        # uses GOOGLE_MAPS_API_KEY when set, else degrades to Nominatim).
        geocoder = make_geocoder(config.geocoder_provider, conn, config)

        now = datetime.now()
        summary = run_all(config, conn, geocoder, now)

        print(
            f"FreeMap scrape — metro={config.metro} db={db_path} at {now.isoformat()}"
        )

        if not summary:
            print("  (no sources enabled — nothing to scrape)")
            return 1

        any_success = False
        for name, result in summary.items():
            deals_found = result["deals_found"]
            upserted = result["upserted"]
            errors = result["errors"]
            if errors is None:
                any_success = True
                flag = " [0 FOUND]" if deals_found == 0 else ""
                print(f"  {name}: found={deals_found} upserted={upserted} ok{flag}")
            else:
                print(
                    f"  {name}: found={deals_found} upserted={upserted} ERROR: {errors}"
                )

        return 0 if any_success else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
