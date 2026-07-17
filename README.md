# FreeMap Seattle

FreeMap surfaces free and buy-one-get-one (BOGO) offers in Seattle. Every
matching offer appears in the list, while geocoded physical offers also appear
on an interactive map.

## Production architecture

```text
GitHub Actions (12h cron) --writes--> Turso <--reads-- Next.js on Vercel
             Python scrapers          libSQL          route handlers + UI
```

- `scrapers/` fetches enabled sources, classifies and geocodes deals, deduplicates
  them, and records every source run.
- Turso is the production source of truth. Local development falls back to
  `db/deals.db`.
- `web-next/` is the production Next.js 16 app. Its API route handlers read
  Turso at request time.
- `.github/workflows/scrape.yml` runs the scraper and health gate every 12 hours.
  `FREEMAP_REQUIRE_TURSO=1` prevents a missing secret from silently writing to
  an ephemeral runner database.
- Each source run records found/upserted counts, mapped pins, geocode failures,
  duration, completion time, and error status.
- The health gate requires all 43 verified `places_brand` deals and at least 40
  current map pins. A partial source or geocoder regression cannot stay green.
- A failed scheduled scrape opens or updates one GitHub issue; the next healthy
  run comments on and closes it.

The scraper and web app communicate only through the database.

## Production sources

`config.toml` enables only sources that meet the Free/BOGO product scope:

| Source | Production role | Health policy |
|---|---|---|
| `places_brand` | Official Chipotle, MOD, Starbucks, and Ulta Free/BOGO rewards expanded to current Seattle storefront pins | Required |
| `reddit` | Free/BOGO posts from `r/Seattle`, filtered with word-boundary matching | Optional because runner IPs may be rate-limited |

The `chains`, `slickdeals`, and `local` parsers remain implemented and tested,
but are disabled. Their broad feeds mostly produced ordinary discounts or
non-deal content, which is outside FreeMap's scope.

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
pipeline normalizes, classifies, geocodes, deduplicates, and upserts those rows.
A source failure is isolated and recorded in `scrape_runs`; it does not erase
another source's successful work.

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

The keyless US Census geocoder is the default. Google is optional; public
Nominatim is retained only for local experimentation because hosted requests
are commonly rejected.

## Validation

```bash
./.venv/bin/pytest -q

cd web-next
npm test
npm run lint
npm run test:e2e
npm run build
```

Source tests use recorded fixtures and mocked HTTP calls. They do not depend on
live websites. Playwright browser tests mock API and map-provider boundaries
while exercising the real UI in Chromium.

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
