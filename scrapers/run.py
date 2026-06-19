"""Orchestrate all sources through the pipeline and record scrape_runs.

Single unattended entrypoint (`python -m scrapers.run`) with zero secrets —
suitable for `meshclaw run TASK.md` on cron. One source failing never aborts
the others; every source's outcome is recorded in scrape_runs.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.db import record_run
from scrapers.pipeline import run_pipeline
from scrapers.sources import reddit, chains

# Module-level registry: source name -> fetch callable.
# Milestone 3 wires only reddit; Milestone 5 adds chains/slickdeals/local;
# Milestone 6 adds the main() CLI entrypoint (which imports connect/init_db/
# load_config/Geocoder). Keep this registry the single source of truth.
SOURCES: dict[str, Callable[..., list[RawDeal]]] = {"reddit": reddit.fetch, "chains": chains.fetch}


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
