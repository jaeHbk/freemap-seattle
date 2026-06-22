# TASK: FreeMap scheduled scrape (MeshClaw)

Unattended scrape of all enabled sources into the SQLite DB. No secrets required
(the geocoder is Nominatim — no API key). Run interactively first to confirm
green, then on cron every 6–12h via `meshclaw run TASK.md`.

## What to do

1. **Run the scrape** from the repo root, using the project virtualenv
   interpreter (the scraper deps — httpx, beautifulsoup4 — live in `.venv/`,
   not in system python):

   ```bash
   cd /Users/jaehunb/projects/freemap
   ./.venv/bin/python -m scrapers.run
   ```

   This loads `config.toml`, opens (and initializes if needed) the DB at
   `config.db_path`, runs every source in `config.sources_enabled` through the
   pipeline, upserts deals (bumping `last_seen`, never duplicating within a
   source), and writes one `scrape_runs` row per source. It prints a per-source
   summary line: `found=<n> upserted=<n> ok|ERROR`.

2. **Capture the exit code.** `0` = at least one source succeeded with no
   exception. `1` = every source errored (total failure).

## How to verify the run

After the command exits, confirm `scrape_runs` recorded this run — one row per
enabled source, newest first:

```bash
cd /Users/jaehunb/projects/freemap
./.venv/bin/python -c "import sqlite3, tomllib; \
cfg = tomllib.load(open('config.toml','rb')); \
db = cfg['meta']['db_path']; \
c = sqlite3.connect(db); c.row_factory = sqlite3.Row; \
rows = c.execute('SELECT source, deals_found, errors, finished_at FROM scrape_runs ORDER BY finished_at DESC LIMIT 20').fetchall(); \
[print(r['source'], 'found='+str(r['deals_found']), 'errors='+repr(r['errors']), r['finished_at']) for r in rows]"
```

Checklist:
- [ ] There is one fresh `scrape_runs` row for **each** source listed in
      `config.sources_enabled` (`reddit`, `chains`, `slickdeals`, `local`).
- [ ] No source is missing a row (a missing row means the orchestration did not
      reach it — investigate `run.py`).

## What to report

Report the per-source summary from the run:

- For each source: `deals_found` and `upserted` count, and `ok`/`ERROR`.
- **Flag** any source where `deals_found == 0` (`[0 FOUND]` in the printed
  summary) — likely a broken selector or a changed payload; the source is
  visible-but-empty, not silently dropped.
- **Flag** any source whose `errors` column is non-null, with the error string.

## Exit policy

- Exit **non-zero only on total failure** — i.e. when every source errored
  (`./.venv/bin/python -m scrapers.run` already returns `1` in that case;
  propagate it).
- A run where some sources found 0 or errored but at least one succeeded is a
  **success with flags** — report the flags, exit `0`.

## Notes for unattended operation

- **Zero secrets.** Do not set or expect any API keys. The User-Agent for all
  outbound requests (including Nominatim) comes from `config.toml`
  (`[meta].user_agent`).
- **Polite + cached.** Geocoding is cache-first and rate-limited
  (`[geocoder].min_interval_seconds`, `max_live_calls`); re-scrapes are nearly
  free because locations repeat.
- **One bad source never aborts the run** — failures are recorded to
  `scrape_runs`, not raised.
- **Wired-source status (as of this version) — TWO live sources:**
  - `slickdeals` → **live** (DealNews, https://www.dealnews.com/) — ~50 online
    deals/run. The real working source.
  - `local` → **live** (My Ballard RSS, https://www.myballard.com/feed/) — ~30
    online deals/run. The feed has no `<location>`, so these are list-view
    deals, not geocoded map pins.
  - `reddit` → **known-blocked, EXPECTED 0-found**: `https://www.reddit.com/r/Seattle/.json`
    returns HTTP 403 to a non-browser User-Agent (Reddit requires a browser UA
    or OAuth). The scraper catches it and reports 0 found — do NOT treat
    reddit's 0/error flag as a regression. Re-enabling needs a browser-like UA
    or Reddit's OAuth API (deferred; OAuth would add a secret).
  - `chains` → **intentionally synthetic, EXPECTED 0-found**: `offers_urls`
    points at a `.example` placeholder that fails DNS and is skipped. Expected
    every run; not a regression until a real chain offers source is wired.
  - **Net:** a healthy run reports `slickdeals` and `local` with deals, and
    `reddit` + `chains` flagged at 0-found. That is the current SUCCESS state.
    Investigate only if `slickdeals` or `local` drops to 0 (changed markup /
    moved feed) or if every source errors (total failure → exit 1).
- **Known tuning note:** the reddit source currently fetches the plain subreddit
  hot feed (no server-side `q=free` filter), so a live run pulls all hot posts
  and relies on the pipeline's classifier to sort deal types. This is fine for
  v1; a server-side `q=free&restrict_sr=1` query or a keyword pre-filter would
  tighten precision later.
- Do not point this at the web layer; the scraper and API share only the DB.
