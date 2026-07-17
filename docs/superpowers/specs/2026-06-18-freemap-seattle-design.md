# FreeMap Seattle — Design (v1)

**Date:** 2026-06-18
**Status:** Approved (design); pending implementation plan
**Working name:** FreeMap Seattle

> **Superseded / historical record (kept as of the 2026-06-18 approval).** The
> shipped system has since diverged from this v1 design and this document is not
> a description of the current architecture. In production today the read layer
> is a **Next.js app** (`web-next/`) with route-handler APIs and a **MapLibre GL**
> map — not the FastAPI `api/` (uvicorn) service or the vanilla-JS/Leaflet `web/`
> frontend described below; deals are stored in **Turso (libSQL)** with a local
> SQLite fallback; the default geocoder is the **keyless US Census** service
> (Nominatim is retained for local use only); and the scheduled scrape runs on
> **GitHub Actions** every 12 hours rather than via MeshClaw. For the current
> architecture and operations see [README.md](../../../README.md) and
> [docs/DEPLOY.md](../../DEPLOY.md).

## 1. Overview

A web app that surfaces free and BOGO (buy-one-get-one) deals. Physical/in-store
deals appear on a **map**; online-only deals appear in a **list/feed**. Deal data
is **scraped** from several sources on a **schedule**, written to a SQLite
database, and served read-only to anonymous visitors.

v1 targets the **Seattle** metro, but the architecture is region-agnostic — the
metro is a single config value. There are no user accounts in v1; visitors browse,
filter, and click through to the source.

The scraper layer is intentionally decoupled from the web layer (they share only
the database). This is what lets the scheduled scrape job be handed to **MeshClaw**
(`meshclaw run TASK.md`, on cron) once the pipeline works interactively. Building
the app happens in Claude Code; running the scrapers unattended is MeshClaw's job.

### Decisions locked during brainstorming

| Decision | Choice |
|---|---|
| Data source | Scraped (Reddit, RetailMeNot/Slickdeals, chain pages, local Seattle sources) |
| Deal scope | Both physical + online; map shows physical, list shows online (+ failed-geocode physical) |
| Geo scope | Seattle first; region-agnostic (metro is config) |
| Users | Anonymous browse only, read-only — no accounts in v1 |
| Freshness | Scheduled re-scrape → DB, per-deal `last_seen`/expiry; stale deals grey out/hide |
| Stack | Python scrapers → SQLite → FastAPI (read-only) → Leaflet JS frontend |
| Pipeline shape | Approach A: shared-contract ETL (all correctness in one pipeline) |
| Geocoder | Nominatim (OpenStreetMap) — free, no key, cache-first, rate-limited |
| `deal_type` enum | `free` / `bogo` / `other` (keep `other`) |

## 2. Architecture & Components

Four well-bounded units. The scraper layer and the web layer never talk directly —
they share only the SQLite database (single source of truth). This decoupling is
what allows MeshClaw to run the scrapers independently of the running web app.

```
scrapers/  (Python — handed to MeshClaw)
  sources/{reddit,slickdeals,chains,local}.py   each: fetch() -> list[RawDeal]
  pipeline.py   normalize -> classify -> geocode -> dedup -> upsert (stamp last_seen)
  run.py        orchestrate all sources through the pipeline
        |
        v  writes
  db/ deals.db  (+ geocode cache, scrape_runs)   SQLite — source of truth
        |
        v  reads (read-only)
  api/  FastAPI   GET /api/deals?type=&category=&bbox= ; GET /api/deals/{id} ; GET /api/meta
        |
        v  fetch()
  web/  Leaflet map + list view (vanilla JS)
        Map: physical deals as clustered pins
        List: online-only (+ failed-geocode physical)
        Filters: deal type, category, freshness
```

| Unit | Job | Depends on | Run by |
|---|---|---|---|
| `scrapers/sources/*` | Fetch raw deals from one source. Knows nothing about geocoding, the DB, or other sources. | The source's website/API only | pipeline |
| `scrapers/pipeline.py` | Shared ETL: normalize → classify → geocode → dedup → upsert. All correctness lives here. | `RawDeal` contract, geocoder, DB | `run.py` |
| `api/` | Read-only HTTP/JSON over the DB. | `deals.db` (read) | uvicorn |
| `web/` | Render map + list, handle filters. | `api/` JSON | browser |

**Extensibility guarantee:** a new source is just a new `sources/foo.py` returning
`list[RawDeal]` — zero changes to pipeline, API, or frontend.

## 3. Data Model & Contracts

### The `RawDeal` contract (what every source returns)

```python
@dataclass
class RawDeal:
    source: str              # "reddit" | "slickdeals" | "chains" | "local"
    source_id: str           # stable ID within source (e.g. reddit post id) — for dedup
    title: str
    url: str
    description: str | None
    raw_location: str | None # free text: "Capitol Hill", "1429 12th Ave", or None
    posted_at: datetime | None
    expires_at: datetime | None
    raw: dict                # original payload, kept for debugging/re-classification
```

The source decides nothing about lat/lng, physical-vs-online, category, or dedup —
the pipeline derives all of those, in one place, consistently.

### The `deals` table (serving record)

```
deals
  id              INTEGER PK
  source          TEXT          UNIQUE(source, source_id) — upsert key
  source_id       TEXT
  dedup_key       TEXT  (indexed)   cross-source dedup
  title           TEXT
  url             TEXT
  description     TEXT
  deal_type       TEXT          "free" | "bogo" | "other"
  category        TEXT          "food" | "retail" | "event" | "other"
  placement       TEXT          "physical" | "online"
  lat, lng        REAL          NULL for online / failed geocode
  raw_location    TEXT
  geocode_status  TEXT          "ok" | "failed" | "n/a"
  posted_at       TIMESTAMP
  expires_at      TIMESTAMP
  first_seen      TIMESTAMP
  last_seen       TIMESTAMP     stamped every scrape run — freshness core
  status          TEXT          "active" | "stale" | "expired"
```

### Supporting tables

- `geocode_cache (raw_location TEXT PK, lat, lng, status)` — geocoding is the
  slow/rate-limited step; cache so re-scrapes don't re-geocode repeated locations.
- `scrape_runs (id, source, started_at, finished_at, deals_found, errors)` — one
  row per source per run, so a broken scraper is visible (0 found / errored) rather
  than silently contributing nothing. MeshClaw reports against this.

### Freshness logic (how a deal dies)

- `expires_at` in the past → **expired** (hidden).
- `last_seen` older than threshold (default: 2 missed scrape cycles, tunable in
  config) → **stale** (greyed, filterable). Handles deals that silently drop out
  of a source.
- Otherwise → **active**.

### Dedup

`dedup_key` = normalized hash of (merchant/title + location + deal_type). Same deal
across Reddit + Slickdeals shares a key; the API collapses to one pin with multiple
source URLs (`alt_urls[]`). Within a source, `UNIQUE(source, source_id)` makes a
re-scrape *update* the row (bump `last_seen`) instead of duplicating it.

## 4. The Pipeline (where all correctness lives)

`run.py` iterates sources; each source's `RawDeal` list flows through five ordered,
independently-testable stages (pure-ish `list[Deal] -> list[Deal]` functions,
testable with fixtures — no network, no DB).

```
RawDeal -> (1) normalize -> (2) classify -> (3) geocode -> (4) dedup -> (5) upsert -> deals.db
```

| # | Stage | What it does | Failure handling |
|---|---|---|---|
| 1 | normalize | Clean text; parse `posted_at`/`expires_at`; derive `category` via keyword rules. | Bad date → `None`, never crash. |
| 2 | classify | Set `placement` (physical if location present/address-like, else online) and `deal_type` (free/bogo/other via keywords). | Ambiguous → `other`/`online` (safe defaults). |
| 3 | geocode | Physical only: `raw_location` → lat/lng. **Cache-first**; live call only on miss. Set `geocode_status`. | Fail → keep deal, `lat/lng=NULL`, `geocode_status="failed"`, demote to list view. Never dropped. |
| 4 | dedup | Compute `dedup_key`; merge same-deal-across-sources into primary + alt URLs. | No collision → stands alone. |
| 5 | upsert | Write on `UNIQUE(source, source_id)`: insert or update + bump `last_seen`. Record run in `scrape_runs`. | Per-deal try/except; one bad row doesn't fail the batch. |

### Cross-cutting principles (robust enough for unattended runs)

- **One source failing never breaks the run.** Each source is wrapped: throw or
  return 0 → log to `scrape_runs` (errors/0-found), move on. A broken scraper is
  visible data, not a crashed job. Essential because MeshClaw runs this unattended.
- **Geocoding is rate-limit-aware.** Cache-first, polite delay between live calls,
  per-run cap. Re-scrapes are nearly free since locations repeat.

### Geocoder: Nominatim (OpenStreetMap)

Free, no API key, no signup. 1 req/sec policy + required User-Agent — fine for our
cached, single-metro volume. Zero secrets to manage, which keeps the MeshClaw
handoff clean. Sits behind `geocode_cache`.

## 5. API & Frontend

### API (FastAPI, read-only — never writes)

| Endpoint | Returns |
|---|---|
| `GET /api/deals?type=&category=&placement=&bbox=&include_stale=` | Filtered deals. `bbox=minLng,minLat,maxLng,maxLat` so the map fetches only what's in view. Always excludes `expired`; excludes `stale` unless `include_stale=true`. Collapses `dedup_key` groups to one record with `alt_urls[]`. |
| `GET /api/deals/{id}` | Full detail for popup/list item. |
| `GET /api/meta` | Counts + last successful scrape time per source (drives a "deals as of …" badge, from `scrape_runs`). |

Thin layer: query SQLite, shape JSON. No business logic — that all lives in the pipeline.

### Frontend (vanilla JS + Leaflet)

```
FreeMap Seattle     [Map] [List]   as of 2pm     <- view toggle + freshness badge
FILTERS  |  Leaflet map: physical deals as clustered pins
 Free    |  pin color = deal_type; greyed = stale (if toggled)
 BOGO    |  click pin -> popup: title · type · category · "seen 2h ago" · link
 Other   |
 Category|  List view = same filters; online-only deals (+ failed-geocode
 show    |              physical) as cards
 stale   |
```

- **Map view:** physical deals as clustered Leaflet markers (OSM tiles — free, no
  key, consistent with Nominatim). Pin color = `deal_type`; greyed = stale (only if
  toggled). Popup shows details + source link(s). Re-queries by `bbox` on pan/zoom.
- **List view:** online-only deals as cards, **plus** physical deals whose geocoding
  failed — so a deal is never lost because we couldn't place it.
- **Filters:** deal type, category, show-stale — apply to both views.
- **Freshness badge:** "deals as of {last scrape}" from `/api/meta` — honest
  expectations on a scraped dataset.

Vanilla JS (no build step) keeps v1 lean. Graduating to a framework later is
additive, not a rewrite.

## 6. Testing, Repo Layout & MeshClaw Handoff

### Repo layout

```
freemap/
  scrapers/
    sources/   reddit.py · chains.py · slickdeals.py · local.py
    contract.py    RawDeal dataclass
    pipeline.py    normalize->classify->geocode->dedup->upsert
    geocode.py     Nominatim client + cache
    db.py          schema, connection, upsert, sweep
    run.py         orchestrate sources -> pipeline; record scrape_runs
  api/             FastAPI app (read-only)
  web/             index.html · map.js · list.js · filters.js · style.css
  db/              deals.db (gitignored; schema.sql committed)
  tests/           unit (stages) · contract · integration · api
  config.toml      metro=seattle, stale_threshold, source list, geocoder cfg
  TASK.md          the MeshClaw handoff spec
  requirements.txt
  README.md
```

### Testing strategy (matches unit boundaries, TDD-friendly)

| Layer | What's tested | How (no network) |
|---|---|---|
| Stage units | normalize/classify/geocode/dedup in isolation | Fixture `RawDeal`s; geocoder mocked. |
| Contract | each `sources/*.py` returns valid `RawDeal`s | Recorded sample payloads, not live sites. |
| Pipeline integration | RawDeal → temp SQLite end-to-end | `:memory:` DB, mocked geocoder. |
| API | filters, bbox, dedup-collapse, stale exclusion | Seeded temp DB, FastAPI TestClient. |
| Freshness | active/stale/expired transitions; re-scrape bumps `last_seen` not dupes | Time-controlled fixtures. |

Scrapers are tested against recorded sample payloads, never live sites — fast,
deterministic, and ToS-polite.

### MeshClaw handoff seam — `TASK.md`

The clean scraper/web split exists for this. Once the pipeline works interactively,
`run.py` is a single unattended entrypoint with **zero secrets** (Nominatim needs no
key). Handoff is:

```
$ meshclaw run TASK.md        # or on cron, every 6–12h
```

`TASK.md` instructs: run `python -m scrapers.run`, verify `scrape_runs` recorded a
successful row per source, report counts, flag any source that found 0 or errored.
MeshClaw's worktree isolation + build/test verification + cron suit this exactly.
`TASK.md` is written as part of the build, ready the moment the pipeline is green.

### Build order (each milestone independently verifiable)

1. **Skeleton + DB** — schema, `RawDeal` contract, empty pipeline stages, failing tests.
2. **Pipeline stages** — TDD each stage against fixtures (no scrapers yet).
3. **Reddit source** — first real source end-to-end → real rows. *Pipeline proven.*
4. **API + frontend** — map + list over real data. *First visible product.*
5. **Remaining sources** — chains → slickdeals → local, each a new module.
6. **`TASK.md` + MeshClaw handoff** — wire the scheduler, verify an unattended run.

## 7. Out of scope for v1 (YAGNI)

User accounts, favorites, alerts, community voting/flagging, nationwide coverage,
online deal redemption. All clean future additions; none load-bearing now.

## 8. Known risks

- **Scraping is brittle / ToS gray area.** Mitigated by: one module per source
  behind a common interface (one breaking doesn't take down the rest), `scrape_runs`
  visibility, recorded-payload tests, and polite rate-limiting. Source selection is
  deliberate; revisit if any source's ToS proves hostile.
- **Geocoding quality** for vague locations ("Capitol Hill") is approximate;
  failures degrade to the list view rather than dropping deals.
- **Cold dataset** until the first scrape runs; the freshness badge sets expectations.
