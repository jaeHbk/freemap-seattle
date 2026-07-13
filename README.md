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

**Geocoding** uses the keyless US Census provider by default, cache-first and
rate-limited; Google and Nominatim adapters are also available.

## Sources

Each source is one module behind a common `fetch(config) -> list[RawDeal]`
interface, configured under `[sources.*]` in `config.toml`. Current status:

| Source | Wired to | Status |
|---|---|---|
| `places_brand` | Curated Seattle storefront offers | **live** — one physical deal per storefront → geocoded map pins |
| `slickdeals` | DealNews front page | **live** — server-rendered offer cards |
| `local` | My Ballard RSS feed | **live** — online deals (feed has no location) |
| `chains` | Tom Douglas happy hours | **live** — one physical deal per named Seattle venue → geocoded map pins |
| `reddit` | `r/Seattle` JSON | **live** — sends a browser UA to clear Reddit's 403; deal-signal pre-filter trims hot-feed noise (a live IP may still be rate-limited) |

Empty sources scrape 0 deals and are recorded as such — expected, not
a failure. Adding a real source is a new `sources/<name>.py` plus a `[sources.<name>]`
config block; the pipeline, API, and frontend need no changes.

## Scheduling (unattended)

The scrape is a deterministic command, so it's driven by a plain OS scheduler. On
macOS, a `launchd` LaunchAgent (`com.freemap.scrape`) runs it every 12 hours and
logs to `logs/`. (In production this is replaced by the GitHub Actions cron — see
**Deploy & operate** above for migration and teardown.)

```bash
launchctl print gui/$(id -u)/com.freemap.scrape        # status + last exit code
launchctl kickstart -k gui/$(id -u)/com.freemap.scrape # run now
tail -f logs/scrape.out.log                            # watch output
```

`TASK.md` is an equivalent spec for an LLM runner (e.g. `meshclaw run TASK.md`) —
worth it only if you want a layer that *reacts* to results (alerting, diagnosing a
broken selector). For a plain scheduled scrape, the LaunchAgent is all you need.

## Hosting the DB (Turso)

Local dev uses the SQLite file `db/deals.db` and needs no setup. For deployment
(where serverless functions have no persistent disk), the same schema runs on
**Turso** (libSQL, SQLite-compatible). The driver swap is env-gated: set both
`TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` and the app uses Turso; leave them
unset and it falls back to the local file. No code change either way.

**1. Provision (one time, by a human with the Turso CLI):**

```bash
turso db create freemap                 # create the database
turso db show freemap --url             # -> TURSO_DATABASE_URL (libsql://...)
turso db tokens create freemap          # -> TURSO_AUTH_TOKEN (secret)
```

**2. Set the env vars.** Copy `.env.example` to `.env.local` (gitignored) and
fill in the two values for local runs against Turso. In CI / Vercel, set the
**same two names** as secrets — `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` (GitHub
Actions secrets for the scrape job; the Vercel dashboard for the read API). Never
commit a token; `.env.example` holds placeholders only.

**3. Apply the schema** (idempotent — re-runnable):

```bash
./.venv/bin/python -m scripts.migrate_turso
```

This runs `db/schema.sql` (the committed source of truth) against the Turso DB.
It refuses to run unless both env vars are present. After it succeeds, point the
scraper and API at Turso by exporting the same vars before running them.

## Deploy & operate

In production the three layers share **Turso** instead of the local SQLite file:
**GitHub Actions** scrapes into Turso on a 12h cron, and **Vercel** hosts the
Next.js app (`web-next/`) whose route handlers read Turso at request time. The
GitHub Actions cron replaces the local `launchd` job below.

```
GitHub Actions (cron 12h) --writes--> Turso <--reads-- Vercel (web-next)
```

Secrets — `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, optional `GOOGLE_MAPS_API_KEY`
— live in GitHub Actions secrets and the Vercel dashboard, referenced by name only;
`.env.example` holds empty placeholders. After each scrape, `python -m scrapers.health`
compares `scrape_runs` against the `config.toml [health]` baseline and fails the
workflow **only** when an *expected* source (`places_brand`, `chains`,
`slickdeals`, `local`) errors or returns 0. Reddit is reported but optional
because runner IPs can be rate-limited.

The full step-by-step runbook (Turso provisioning, seeding, Vercel project setup,
GitHub Actions secrets, reading health, and **tearing down the old launchd job**) is
in **[`docs/DEPLOY.md`](docs/DEPLOY.md)**. See `.env.example` for every env var.

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
