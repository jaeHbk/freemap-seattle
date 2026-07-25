# Deploy and operate

FreeMap production has three pieces:

- Turso stores deals, geocode cache entries, and scrape history.
- GitHub Actions writes to Turso every 12 hours.
- Vercel hosts `web-next/` and reads Turso at request time.

All credentials live in provider secret stores. Never commit or print a Turso
token.

## 1. Provision Turso

```bash
turso db create freemap
turso db show freemap --url
turso db tokens create freemap
```

Export the returned values in the current shell, then apply the schema:

```bash
export TURSO_DATABASE_URL='libsql://...'
export TURSO_AUTH_TOKEN='...'
export FREEMAP_REQUIRE_TURSO=1
./.venv/bin/python -m scripts.migrate_turso
```

The migration is idempotent, creates candidate/evidence staging tables, adds
nullable publication-provenance and scrape-telemetry columns, and verifies the
remote schema with a read-back query.
A successful run prints:

```text
Turso schema applied and verified (idempotent).
```

## 2. Seed and verify Turso

With the same environment:

```bash
./.venv/bin/python -m scrapers.run
./.venv/bin/python -m scrapers.health
./.venv/bin/python -m scrapers.quality
```

`places_brand` is required and should publish the configured geocoded Seattle
pins. All other adapters are optional discovery inputs; pending or rejected
candidates do not make the health check fail.

Verify scoped rows and coordinates:

```bash
turso db shell freemap \
  "SELECT source, deal_type, COUNT(*) AS deals, \
   SUM(CASE WHEN lat IS NOT NULL AND lng IS NOT NULL THEN 1 ELSE 0 END) AS pins \
   FROM deals GROUP BY source, deal_type; \
   SELECT source, deals_found, candidates_staged, deals_upserted, \
   candidates_pending, candidates_rejected, map_pins, geocode_failures, \
   duration_ms, errors, finished_at \
   FROM scrape_runs ORDER BY id DESC LIMIT 4;"
```

## 3. Configure GitHub Actions

Add these repository Actions secrets:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `GOOGLE_MAPS_API_KEY` only when the Google provider is selected

The workflow sets `FREEMAP_REQUIRE_TURSO=1`, so missing or incomplete Turso
secrets fail before any SQLite fallback can occur.

Dispatch `.github/workflows/scrape.yml` once and wait for all three steps:

1. `Scrape into Turso`
2. `Source health check`
3. `Information quality audit`

The health baseline is:

- `expected = ["places_brand"]`
- `optional = ["reddit", "chains", "slickdeals", "local"]`
- `minimum_deals = { places_brand = 44 }`
- `minimum_pins = { places_brand = 40 }`

Health fails when the latest required run is missing, stale, errored, discovers
or stages fewer than all 44 configured candidates, or produces fewer than 40
current map pins. Published count may be lower because candidates that fail a
publication gate remain pending or rejected.
The `places_brand` source also fails closed when official terms have not been
reverified within 30 days or an explicit `expires_at` has passed. Follow
`TASK.md` to recheck terms and storefronts before the deadline.
Every workflow run writes discovery/publication/pin/geocode-failure/duration
telemetry and the database quality audit to its GitHub Actions summary.

On failure, the workflow opens or updates the single issue
`[FreeMap] Scheduled scrape unhealthy` with the latest run link. Repeated
failures update that issue rather than creating duplicates. The next successful
run records its recovery link and closes the issue. Workflow failure email or
watch notifications remain available through normal GitHub settings.

## 4. Deploy Vercel

Import the GitHub repository and configure:

- Root Directory: `web-next`
- Framework: Next.js
- `TURSO_DATABASE_URL`: Production, Preview, Development
- `TURSO_AUTH_TOKEN`: Production, Preview, Development

The route handlers are dynamic and read Turso for each request. The Vercel
runtime refuses to fall back to a local database when `TURSO_DATABASE_URL` is
missing.

After deployment, verify:

```bash
curl --fail --silent --show-error https://YOUR_DOMAIN/api/meta
curl --fail --silent --show-error https://YOUR_DOMAIN/api/deals
curl --fail --silent --show-error \
  'https://YOUR_DOMAIN/api/deals?bbox=-122.45,47.50,-122.20,47.75'
```

Also open the production page at desktop and mobile widths. Confirm the map
tiles render, Seattle pins are visible, filters work, list/map tabs are
keyboard-operable, and no controls overlap.

## 5. Retire the legacy scheduler

Only after the manually dispatched GitHub Actions run is green and Turso shows
fresh rows:

```bash
launchctl bootout gui/$(id -u)/com.freemap.scrape
rm ~/Library/LaunchAgents/com.freemap.scrape.plist
```

Verify it is gone:

```bash
launchctl print gui/$(id -u)/com.freemap.scrape
```

`launchctl print` should report that the service was not found. GitHub Actions
is then the sole production scheduler.

## 6. Routine checks

Inspect recent source health:

```bash
turso db shell freemap \
  "SELECT source, finished_at, deals_found, candidates_staged, \
   deals_upserted, candidates_pending, candidates_rejected, map_pins, \
   geocode_failures, duration_ms, errors \
   FROM scrape_runs ORDER BY id DESC LIMIT 10;"
```

Inspect the app's serving metadata:

```bash
curl --fail --silent --show-error https://YOUR_DOMAIN/api/meta
```

Keep broad discovery enabled, but do not bypass candidate publication policy for
`reddit`, `chains`, `slickdeals`, or `local`. Review pending/rejected counts and
source markup changes when their candidate volume shifts unexpectedly.
