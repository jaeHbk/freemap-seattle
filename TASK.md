# TASK: FreeMap manual scrape

Use this procedure for a local verification run or an operator-triggered Turso
seed. Production scheduling is owned by `.github/workflows/scrape.yml`.

## Run

From the repository root:

```bash
./.venv/bin/python -m scrapers.run
./.venv/bin/python -m scrapers.health
```

Without Turso variables, this writes to `db/deals.db`. For a remote seed, export
both credentials and require the remote path:

```bash
export TURSO_DATABASE_URL='libsql://...'
export TURSO_AUTH_TOKEN='...'
export FREEMAP_REQUIRE_TURSO=1
./.venv/bin/python -m scrapers.run
./.venv/bin/python -m scrapers.health
```

Never commit or print a token.

## Expected result

The enabled source set is:

- `places_brand`: required; should produce the configured Seattle storefront
  Free/BOGO rows and geocoded map pins.
- `reddit`: optional; may produce zero rows or be rate-limited.

The scrape command prints `found`, `upserted`, `pins`, `geocode_failed`,
`duration_ms`, and `ok` or `ERROR` for each source. The health command must
print `[ok] places_brand` with `found=43`, at least `pins=39`, and finish with
`HEALTHY`. Reddit is reported as `[opt]` and does not control the exit code.

Any missing, errored, stale, sub-43-fetched, sub-43-stored, or sub-39-pin
`places_brand` run is a failure.

## Reverify official offers

Before an offer reaches `verification_max_age_days = 30`:

1. Open each brand's configured official terms URL and confirm the offer,
   eligibility, redemption steps, and any expiration.
2. Check the official store locator and update `locations`, deal/pin floors, and
   geocoder evidence when storefronts changed.
3. Set `verified_at` to the review date. Add or update `expires_at` for finite
   promotions; a date-only value is valid through the end of that date.
4. Run the scrape and health commands above. A missing, malformed, future,
   overdue, or expired verification fails the required source without refreshing
   old rows.

## Verify rows

For local SQLite:

```bash
./.venv/bin/python -c "import sqlite3; c=sqlite3.connect('db/deals.db'); print(c.execute(\"SELECT source, COUNT(*) FROM deals GROUP BY source\").fetchall())"
```

For Turso:

```bash
turso db shell freemap \
  "SELECT source, COUNT(*) AS deals FROM deals GROUP BY source; \
   SELECT source, deals_found, deals_upserted, map_pins, geocode_failures, \
   duration_ms, errors, finished_at FROM scrape_runs \
   ORDER BY id DESC LIMIT 4;"
```
