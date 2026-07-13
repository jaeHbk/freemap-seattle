# Deploy & operate

FreeMap Seattle runs as three decoupled pieces that share only the database:

- **Turso (libSQL)** — the single source of truth in production (replaces the local
  `db/deals.db` file, which serverless functions can't persist).
- **GitHub Actions** — a scheduled job that scrapes into Turso every 12h
  (replaces the machine-local `launchd` job).
- **Vercel** — hosts the Next.js app (`web-next/`), whose route handlers read Turso
  over HTTP at request time.

```
GitHub Actions (cron 12h) --writes--> Turso (libSQL) <--reads-- Vercel (web-next)
        scrapers.run                  deals, scrape_runs            route handlers
```

All secrets (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, optional `GOOGLE_MAPS_API_KEY`)
are referenced by name only. They live in GitHub Actions secrets and the Vercel
dashboard — never in the repo. `.env.example` holds empty placeholders; `.env.local`
is gitignored. **Never commit a real token.**

---

## 1. Provision Turso (one time, human with the Turso CLI)

```bash
turso db create freemap                 # create the database
turso db show freemap --url             # -> TURSO_DATABASE_URL (libsql://...)
turso db tokens create freemap          # -> TURSO_AUTH_TOKEN (secret, shown once)
```

Apply the schema (idempotent — `db/schema.sql` is all `CREATE ... IF NOT EXISTS`):

```bash
export TURSO_DATABASE_URL='libsql://...'      # from `turso db show`
export TURSO_AUTH_TOKEN='...'                 # from `turso db tokens create`
./.venv/bin/python -m scripts.migrate_turso
```

`migrate_turso` refuses to run unless both vars are set, and does a read-back SELECT
to prove the schema reached the remote (a clean return alone is not proof). On success
it prints `Turso schema applied and verified (idempotent).` without echoing the URL/token.

## 2. Seed the data (run the scraper once against Turso)

With the same two vars still exported, `scrapers/db.py connect()` auto-detects them and
routes all writes to Turso instead of the local file:

```bash
./.venv/bin/python -m scrapers.run
```

Expect per-source lines like `places_brand: found=9 upserted=9 ok`. All five
configured sources run; Reddit may report 0 when the runner IP is rate-limited.
Exit code is `0` if any source succeeded.

## 3. Vercel (the read app)

1. Import the GitHub repo at <https://vercel.com/new>.
2. **Root Directory: `web-next`** (set in the Vercel dashboard, Project Settings →
   General → Root Directory). Next.js is auto-detected — no `vercel.json` is needed.
3. Add environment variables (Project Settings → Environment Variables), all
   environments (Production + Preview):
   - `TURSO_DATABASE_URL`
   - `TURSO_AUTH_TOKEN`
   - `GOOGLE_MAPS_API_KEY` *(optional — only if a keyed geocoder/places provider is
     enabled; the read app itself does not require it)*
4. Deploy. The route handlers declare `export const dynamic = "force-dynamic"`
   (`web-next/app/api/deals/route.ts`), so each request reads live from Turso — no stale
   cached build output.

## 4. GitHub Actions secrets (the scheduled scrape)

The committed workflow `.github/workflows/scrape.yml` runs `python -m scrapers.run` on a
12h cron (and on `workflow_dispatch`). Add the **same three** secrets at
Repo → Settings → Secrets and variables → Actions → New repository secret:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `GOOGLE_MAPS_API_KEY` *(optional; only if the keyed geocoder/places provider is on)*

The workflow exposes them to the run via `env: ${{ secrets.NAME }}` — they never appear
in logs or the repo. Run it once by hand: Actions tab → the scrape workflow → **Run
workflow** (`workflow_dispatch`), then confirm Turso counts increased.

## 5. Reading health

After each scrape the workflow runs the health check (`python -m scrapers.health`). It
reads the latest `scrape_runs` row per source and compares against the baseline in
`config.toml [health]`:

- `expected` = sources that MUST be healthy (`places_brand`, `chains`,
  `slickdeals`, `local`).
- `optional` = sources that are reported but do not fail the workflow (`reddit`,
  because a live runner IP may be rate-limited).

It exits non-zero (failing the workflow, which surfaces a GitHub notification)
**only** when an expected source errored or returned 0 deals.

`scrape_runs` is the durable per-source log (columns: `source`, `started_at`,
`finished_at`, `deals_found`, `errors`; `errors IS NULL` means that run succeeded).
Inspect it directly any time:

```bash
turso db shell freemap \
  "SELECT source, finished_at, deals_found, errors FROM scrape_runs \
   ORDER BY finished_at DESC LIMIT 10"
```

The Next app also exposes a recency badge via `/api/meta`.

## 6. Tear down the old launchd job (human step — do this only after GH Actions is green)

The old scheduler is a machine-local `launchd` LaunchAgent (`com.freemap.scrape`). It is
**not** in the repo and is a live system job — leave it running until the GitHub Actions
scrape has succeeded at least once against Turso, then the human removes it:

```bash
# 1. Confirm the GH Actions scrape ran green and Turso has fresh rows first.
launchctl bootout gui/$(id -u)/com.freemap.scrape          # stop & unload the agent
rm ~/Library/LaunchAgents/com.freemap.scrape.plist         # remove the plist
```

After teardown, `launchctl print gui/$(id -u)/com.freemap.scrape` should report it as not
found. The local `logs/` dir (gitignored) can also be removed. From then on, GitHub
Actions is the only scheduler.

---

See `.env.example` for the full list of environment variables (placeholders only).
