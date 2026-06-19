# FreeMap Seattle

A web app surfacing **free** and **BOGO** deals. Physical/in-store deals show on a
**map**; online-only deals (and physical deals we couldn't geocode) show in a
**list**. Data is scraped on a schedule into SQLite and served read-only to
anonymous visitors. v1 targets **Seattle**, but the metro is a single config value
— the architecture is region-agnostic.

No accounts. No secrets (the geocoder is Nominatim — no API key).

## Architecture

```
scrapers/  (Python — handed to MeshClaw)
  sources/{reddit,chains,slickdeals,local}.py   each: fetch(config) -> list[RawDeal]
  pipeline.py   normalize -> classify -> geocode -> dedup -> upsert (stamp last_seen)
  run.py        orchestrate all sources -> pipeline; record scrape_runs
      |  writes
      v
  db/deals.db   (+ geocode_cache, scrape_runs)   SQLite — source of truth
      |  reads (read-only)
      v
  api/  FastAPI   GET /api/deals ; /api/deals/{id} ; /api/meta
      |
      v
  web/  Leaflet map + list (vanilla JS, no build step)
```

The scraper layer and web layer never talk directly — they share only the DB.
That decoupling is what lets MeshClaw run the scrapers unattended on cron.

## Requirements

- Python 3.14.x
- Pinned deps in `requirements.txt`

## Setup

```bash
cd /path/to/freemap
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Initialize the database

The DB lives at the path in `config.toml` (`[meta].db_path`, default
`db/deals.db`). It is gitignored; the schema (`db/schema.sql`) is committed.
`python -m scrapers.run` calls `init_db()` automatically, so the first scrape
creates and initializes the DB. To initialize without scraping:

```bash
python -c "from scrapers.db import connect, init_db; init_db(connect('db/deals.db'))"
```

## Run the scrapers

```bash
python -m scrapers.run                       # uses config.toml + config.db_path
python -m scrapers.run --config config.toml --db db/deals.db   # explicit
python -m scrapers.run --help                # options
```

Each source runs through the shared pipeline (normalize -> classify -> geocode ->
dedup -> upsert). One source failing never aborts the others; every source gets a
`scrape_runs` row (errored or 0-found sources are *visible*, not silently
dropped). A re-scrape **bumps `last_seen`**, it does not duplicate rows. Exit code
is `0` if at least one source succeeded, `1` only if every source errored.

## Serve the API + frontend

```bash
uvicorn api.main:app --reload
```

Then open <http://127.0.0.1:8000/> — FastAPI serves `web/` (the Leaflet map +
list) at `/` via StaticFiles, and the JSON API at:

- `GET /api/deals?type=&category=&placement=&bbox=&include_stale=`
  (`bbox=minLng,minLat,maxLng,maxLat`; always excludes expired; excludes stale
  unless `include_stale=true`; collapses cross-source dups into one record with
  `alt_urls[]`)
- `GET /api/deals/{id}`
- `GET /api/meta` (per-source counts + last successful scrape time)

The API is **read-only** — it never writes. All correctness lives in the pipeline.

## Repoint to a different metro

The metro is config, not code. Edit `config.toml`:

```toml
[meta]
metro = "portland"          # was "seattle"
db_path = "db/deals.db"
```

Then update the per-source settings under `[sources.*]` (subreddits, offer URLs,
feed URLs, etc.) to the new metro's sources, and re-run `python -m scrapers.run`.
No code changes are required to change region — the pipeline, API, and frontend
are region-agnostic.

## Freshness

- **expired** — `expires_at` is in the past → hidden.
- **stale** — `last_seen` older than `[freshness].stale_after_hours` (default 24)
  → greyed and filterable (`include_stale=true` to show).
- **active** — otherwise.

Status is computed at read time, so it is always current relative to "now".

## Tests (offline only)

```bash
pytest -q
```

All tests run offline: sources are tested against recorded payloads in
`tests/fixtures/` with `httpx.get` monkeypatched, and geocoding uses a
`FakeGeocoder` — **never** live sites or live Nominatim.

## MeshClaw handoff (scheduled, unattended)

Once the pipeline is green, the scrape is a single unattended entrypoint with
**zero secrets**. Hand it to MeshClaw:

```bash
meshclaw run TASK.md          # or on cron, every 6–12h
```

`TASK.md` instructs MeshClaw to run `python -m scrapers.run`, verify `scrape_runs`
has a row per enabled source for the run, report per-source counts, flag any
source that found 0 or errored, and exit non-zero only on total failure.
MeshClaw's worktree isolation + cron fit this exactly. Nothing in the scrape path
needs an API key.
