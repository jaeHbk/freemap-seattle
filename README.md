# FreeMap Seattle

FreeMap surfaces verified free and buy-one-get-one (BOGO) offers in Seattle.
Every published offer appears in the list, while geocoded physical offers also
appear on an interactive map.

## Production architecture

```text
GitHub Actions (12h cron) --writes--> Turso <--reads-- Next.js on Vercel
             Python scrapers          libSQL          route handlers + UI
```

- `scrapers/` fetches enabled sources, persists candidates and evidence, applies
  publication policy, geocodes in-scope locations, and records every source run.
- Turso is the production source of truth. Local development falls back to
  `db/deals.db`.
- `web-next/` is the production Next.js 16 app. Its API route handlers read
  Turso at request time.
- `.github/workflows/scrape.yml` runs the scraper, health gate, and quality audit
  every 12 hours.
  `FREEMAP_REQUIRE_TURSO=1` prevents a missing secret from silently writing to
  an ephemeral runner database.
- Each source run records discovered, staged, published, pending, and rejected
  counts plus mapped pins, geocode failures, duration, and error status.
- The health gate requires discovery and staging of all 44 verified
  `places_brand` candidates plus at least 40 current map pins. Candidates may
  remain pending when they fail publication gates without making a healthy
  discovery run fail.
- A database quality audit rejects any public row without accepted evidence,
  Free/BOGO scope, official or corroborated verification, and a score of 90+.
- A failed scheduled scrape opens or updates one GitHub issue; the next healthy
  run comments on and closes it.

The scraper and web app communicate only through the database.

## Production sources

`config.toml` enables broad discovery without granting every source permission
to publish:

| Source | Production role | Health policy |
|---|---|---|
| `places_brand` | Current official terms for Chipotle, Frye Art Museum, MOD, Starbucks, and Ulta, expanded to Seattle locations | Publishes after verification and location gates; required |
| `reddit` | Free/BOGO community posts from `r/Seattle` | Staged pending independent corroboration |
| `chains` | Official restaurant offer pages | Staged; ordinary discounts are rejected |
| `slickdeals` | Broad aggregator listings | Staged pending independent corroboration |
| `local` | Seattle editorial/RSS coverage | Staged pending independent corroboration |

Matching evidence from two independent non-official sources can publish. A
single community, editorial, or aggregator observation cannot.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scrapers.run

cd web-next
npm ci
npm run dev
```

Open <http://localhost:3000>. With no Turso variables, Python and Next.js use the
local SQLite database at `db/deals.db`.

To test against Turso, set both `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`.
Set `FREEMAP_REQUIRE_TURSO=1` in automation so incomplete credentials fail
closed instead of falling back to SQLite.

## Data behavior

Each enabled source implements `fetch(config) -> list[RawDeal]`. The shared
pipeline normalizes each observation into a candidate, persists evidence,
applies hard scope/freshness/location gates, and materializes accepted
candidates into `deals`. A source failure is isolated and recorded in
`scrape_runs`; it does not erase another source's successful work.

The read API is available under the Next.js app:

- `GET /api/deals?type=&category=&placement=&bbox=&include_stale=`
- `GET /api/deals/{id}`
- `GET /api/geocode?q=` for Seattle neighborhood and address lookup
- `GET /api/meta` for current source counts, freshness, and latest-run telemetry

`bbox` uses `minLng,minLat,maxLng,maxLat` and is pushed into SQL. The current UI
loads the small map payload once and lets MapLibre cluster and cull offscreen
markers, avoiding a request on every pan. Bounded API clients can use `bbox`.
Users can search a Seattle neighborhood or address, or share browser location,
to focus the map and sort the complete list by distance. The active view,
filters, chosen location, open deal, and map position are mirrored to the URL,
so a shared or bookmarked link restores that state and browser back/forward
works.

Freshness is computed at read time:

- `expired`: hidden
- `stale`: hidden unless `include_stale=true`
- `active`: shown

Verified brand rows also carry structured eligibility, redemption instructions,
and verification dates. The list and map both open the same deal-detail drawer;
community rows without structured terms link back to their source.

Official brand terms fail closed after 30 days without human reverification.
Malformed, future-dated, overdue, or explicitly expired terms stop the required
source before it refreshes `last_seen`; prior rows then become stale and disappear
within 24 hours. Date-only `expires_at` values remain valid through that full day.

The keyless US Census geocoder is the default. Google is optional; public
Nominatim is retained only for local experimentation because hosted requests
are commonly rejected.

## Validation

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m scrapers.quality

cd web-next
npm test
npm run lint
npm run test:e2e
npm run build
```

Source tests use recorded fixtures and mocked HTTP calls. They do not depend on
live websites. Playwright browser tests mock API and map-provider boundaries
while exercising the real UI in Chromium.

The reproducible before/after measurements and their limitations are in
[docs/QUALITY_REPORT.md](docs/QUALITY_REPORT.md).

## Deploy and operate

The complete provisioning, secret setup, deployment, health verification, and
legacy scheduler teardown procedure is in [docs/DEPLOY.md](docs/DEPLOY.md).

## Repository layout

```text
scrapers/       source adapters, scope rules, pipeline, Turso adapter, health
scripts/        Turso schema migration
db/schema.sql   committed database schema
web-next/       production Next.js app
tests/          Python unit and integration tests
docs/           deployment and design documentation
config.toml     source, geocoder, freshness, and health policy
```
