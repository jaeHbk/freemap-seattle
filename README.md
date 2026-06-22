# FreeMap Seattle

A small web app that surfaces **free** and **BOGO** deals. Physical deals appear on a
**map**; online deals (and physical deals that couldn't be geocoded) appear in a
**list**. Deals are scraped on a schedule into SQLite and served read-only — no
accounts, no API keys. v1 targets **Seattle**, but the metro is a single config
value, so the architecture is region-agnostic.

## Architecture

```
scrapers/  (Python)
  sources/{reddit,chains,slickdeals,local}.py   each: fetch(config) -> list[RawDeal]
  pipeline.py   normalize -> classify -> geocode -> dedup -> upsert
  run.py        orchestrate sources -> pipeline; record scrape_runs
      |  writes
      v
  db/deals.db   (+ geocode_cache, scrape_runs)   SQLite — single source of truth
      |  reads (read-only)
      v
  api/  FastAPI   GET /api/deals · /api/deals/{id} · /api/meta
      |
      v
  web/  Leaflet map + list  (vanilla JS, no build step)
```

The scraper and web layers never talk directly — they share only the database.
That decoupling is what lets the scrape run unattended on a schedule (see below)
while the API serves whatever is currently in the DB. **All correctness lives in
the pipeline; the API is read-only.**

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m scrapers.run          # scrape into db/deals.db (creates it if needed)
uvicorn api.main:app --reload   # serve at http://127.0.0.1:8000/
```

Open <http://127.0.0.1:8000/> — FastAPI serves the Leaflet UI at `/` and the JSON
API alongside it.

> Tests, the scheduler, and `TASK.md` invoke the interpreter as
> `./.venv/bin/python` so they work without an activated shell.

## How it works

**Scrape.** `python -m scrapers.run` runs every enabled source through the shared
pipeline (`normalize → classify → geocode → dedup → upsert`). One source failing
never aborts the others — every source gets a `scrape_runs` row, so an errored or
empty source is *visible*, not silently dropped. A re-scrape **bumps `last_seen`**
rather than duplicating rows. Exit code is `0` if any source succeeded, `1` only
if all errored.

**API** (read-only):

- `GET /api/deals?type=&category=&placement=&bbox=&include_stale=` —
  `bbox=minLng,minLat,maxLng,maxLat`; always excludes expired; excludes stale
  unless `include_stale=true`; collapses cross-source duplicates into one record
  with `alt_urls[]`.
- `GET /api/deals/{id}`
- `GET /api/meta` — per-source counts + last successful scrape time.

**Freshness** is computed at read time, so it is always current:

- **expired** — `expires_at` in the past → hidden.
- **stale** — `last_seen` older than `[freshness].stale_after_hours` (default 24)
  → greyed, shown only with `include_stale=true`.
- **active** — otherwise.

**Geocoding** uses Nominatim (no key), cache-first and rate-limited; re-scrapes are
nearly free because locations repeat.

## Sources

Each source is one module behind a common `fetch(config) -> list[RawDeal]`
interface, configured under `[sources.*]` in `config.toml`. Current status:

| Source | Wired to | Status |
|---|---|---|
| `slickdeals` | DealNews front page | **live** — server-rendered offer cards |
| `local` | My Ballard RSS feed | **live** — online deals (feed has no location) |
| `reddit` | `r/Seattle` JSON | blocked — Reddit returns 403 to a non-browser UA; needs a browser UA or OAuth |
| `chains` | — | synthetic placeholder; no scrapeable Seattle-wide chain offers page found |

Blocked/placeholder sources scrape 0 deals and are recorded as such — expected, not
a failure. Adding a real source is a new `sources/<name>.py` plus a `[sources.<name>]`
config block; the pipeline, API, and frontend need no changes.

## Scheduling (unattended)

The scrape is a deterministic command, so it's driven by a plain OS scheduler. On
macOS, a `launchd` LaunchAgent (`com.freemap.scrape`) runs it every 12 hours and
logs to `logs/`:

```bash
launchctl print gui/$(id -u)/com.freemap.scrape        # status + last exit code
launchctl kickstart -k gui/$(id -u)/com.freemap.scrape # run now
tail -f logs/scrape.out.log                            # watch output
```

`TASK.md` is an equivalent spec for an LLM runner (e.g. `meshclaw run TASK.md`) —
worth it only if you want a layer that *reacts* to results (alerting, diagnosing a
broken selector). For a plain scheduled scrape, the LaunchAgent is all you need.

## Repoint to a different metro

The metro is config, not code. In `config.toml` set `[meta].metro`, update the
per-source URLs under `[sources.*]`, and re-run the scrape. No code changes.

## Tests (offline only)

```bash
pytest -q          # Python: pipeline, sources, API
node web/*.test.js # frontend pure-function helpers
```

Sources are tested against recorded payloads in `tests/fixtures/` with `httpx.get`
monkeypatched and a `FakeGeocoder` — **never** live sites or live Nominatim.

## Layout

```
scrapers/   sources + pipeline + run.py + db.py + geocode.py + config.py
api/        FastAPI app (read-only)
web/        index.html · map.js · list.js · filters.js · style.css (+ *.test.js)
db/         schema.sql (committed); deals.db is generated, gitignored
docs/       design spec + implementation plan
config.toml · TASK.md · requirements.txt
```
