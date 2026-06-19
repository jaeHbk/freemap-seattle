# FreeMap Seattle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build FreeMap Seattle v1 — a web app that scrapes free/BOGO deals, stores them in SQLite, and serves them read-only to anonymous visitors as a Leaflet map (physical deals) plus a list (online + failed-geocode physical deals).

**Architecture:** Shared-contract ETL (Approach A). Each source returns `list[RawDeal]`; one pipeline does normalize → classify → geocode → dedup → upsert, so all correctness lives in `scrapers/pipeline.py`. The scraper layer is decoupled from the read-only FastAPI/Leaflet web layer (they share only `db/deals.db`), so the scheduled scrape job can run unattended via `meshclaw run TASK.md` on cron with zero secrets.

**Tech Stack:** Python 3.14 (stdlib `tomllib`, `sqlite3`, `dataclasses`), FastAPI 0.137.2 + uvicorn 0.49.0, httpx 0.28.1, BeautifulSoup4 4.15.0, pytest 9.1.0. Frontend: vanilla JS + Leaflet 1.9.4 + Leaflet.markercluster 1.5.3 via unpkg (no build step). Geocoder: Nominatim (no key), cache-first, rate-limited.

**Build order (each milestone independently verifiable):** M1 Skeleton+DB → M2 Pipeline stages + `run_pipeline`/`fetch_all_deals` → M3 Reddit source + orchestration → M4 API + frontend → M5 remaining sources → M6 `TASK.md` + MeshClaw handoff.

---

## Milestone 1: Skeleton + DB

**Goal:** Stand up the repo scaffold so the `scrapers` package imports cleanly, the SQLite schema creates all three tables, and `load_config()` returns the canonical flat `Config` — all verified by green pytest.

### Task 1.1: Initialize repo and Python tooling files

**Files:** `/Users/jaehunb/projects/freemap/.gitignore`, `/Users/jaehunb/projects/freemap/requirements.txt`, `/Users/jaehunb/projects/freemap/pytest.ini`, `/Users/jaehunb/projects/freemap/README.md`

- [ ] **Step 1 — confirm the repo exists and is empty of code.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git rev-parse --is-inside-work-tree 2>/dev/null || git init
  ls -A /Users/jaehunb/projects/freemap
  ```
  Expected: prints `true` (or initializes git), and the listing shows only `docs/` and `.git/` (no source packages yet).

- [ ] **Step 2 — create `.gitignore`.** Write `/Users/jaehunb/projects/freemap/.gitignore` with exactly:
  ```gitignore
  __pycache__/
  *.py[cod]
  .pytest_cache/
  .venv/
  venv/
  *.egg-info/
  # SQLite database is generated; schema.sql is committed instead
  db/deals.db
  db/deals.db-journal
  db/deals.db-wal
  db/deals.db-shm
  .DS_Store
  ```

- [ ] **Step 3 — create `requirements.txt`** with the pinned deps verbatim. Write `/Users/jaehunb/projects/freemap/requirements.txt`:
  ```text
  fastapi==0.137.2
  uvicorn[standard]==0.49.0
  httpx==0.28.1
  beautifulsoup4==4.15.0
  pytest==9.1.0
  ```

- [ ] **Step 4 — create `pytest.ini`** so tests run from the repo root and discover the `tests/` dir. Write `/Users/jaehunb/projects/freemap/pytest.ini`:
  ```ini
  [pytest]
  testpaths = tests
  python_files = test_*.py
  python_functions = test_*
  addopts = -ra
  ```

- [ ] **Step 5 — create a minimal `README.md`.** Write `/Users/jaehunb/projects/freemap/README.md`:
  ```markdown
  # FreeMap Seattle

  Scraped free/BOGO deals. Physical deals on a Leaflet map; online (and
  failed-geocode physical) deals in a list. Seattle-first, region-agnostic
  (metro is config). Anonymous read-only browse, no accounts.

  Architecture: Python scrapers -> SQLite -> read-only FastAPI -> vanilla-JS
  Leaflet frontend. All correctness lives in `scrapers/pipeline.py` (shared
  contract ETL). The scraper layer is decoupled so it can run unattended via
  `meshclaw run TASK.md` on cron with zero secrets.

  ## Setup

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

  ## Run the tests

  ```bash
  pytest
  ```

  See `docs/superpowers/specs/2026-06-18-freemap-seattle-design.md` for the full design.
  ```

- [ ] **Step 6 — verify Python version is 3.14.x** (we rely on stdlib `tomllib` and PEP 604 `X | None` syntax). Run:
  ```bash
  python3 --version
  ```
  Expected: `Python 3.14.5` (any 3.14.x is acceptable; `tomllib` requires 3.11+).

- [ ] **Step 7 — commit.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add .gitignore requirements.txt pytest.ini README.md && git commit -m "chore: scaffold repo tooling (gitignore, requirements, pytest, README)"
  ```
  Expected: one commit created listing 4 files.

### Task 1.2: Create the `scrapers` package and `contract.py` dataclasses

**Files:** `/Users/jaehunb/projects/freemap/scrapers/__init__.py`, `/Users/jaehunb/projects/freemap/scrapers/contract.py`, `/Users/jaehunb/projects/freemap/tests/__init__.py` (none), `/Users/jaehunb/projects/freemap/tests/test_contract_import.py`

- [ ] **Step 1 — create the empty package marker.** Write `/Users/jaehunb/projects/freemap/scrapers/__init__.py`:
  ```python
  ```
  (An empty file — this makes `scrapers` an importable package.)

- [ ] **Step 2 — write the failing import test FIRST.** Write `/Users/jaehunb/projects/freemap/tests/test_contract_import.py`:
  ```python
  from datetime import datetime

  from scrapers.contract import RawDeal, Deal


  def test_rawdeal_minimal_fields_and_defaults():
      raw = RawDeal(source="reddit", source_id="abc123", title="Free coffee", url="http://x")
      assert raw.source == "reddit"
      assert raw.source_id == "abc123"
      assert raw.title == "Free coffee"
      assert raw.url == "http://x"
      assert raw.description is None
      assert raw.raw_location is None
      assert raw.posted_at is None
      assert raw.expires_at is None
      assert raw.raw == {}


  def test_rawdeal_raw_dict_is_per_instance():
      a = RawDeal(source="s", source_id="1", title="t", url="u")
      b = RawDeal(source="s", source_id="2", title="t", url="u")
      a.raw["k"] = "v"
      assert b.raw == {}  # default_factory, not a shared mutable default


  def test_deal_required_and_optional_fields():
      deal = Deal(
          source="reddit",
          source_id="abc123",
          title="Free coffee",
          url="http://x",
          description=None,
          deal_type="free",
          category="food",
          placement="physical",
          lat=47.6,
          lng=-122.3,
          raw_location="Capitol Hill",
          geocode_status="ok",
          posted_at=datetime(2026, 6, 18, 9, 0, 0),
          expires_at=None,
      )
      assert deal.deal_type == "free"
      assert deal.placement == "physical"
      assert deal.geocode_status == "ok"
      assert deal.dedup_key is None  # defaults to None until dedup() sets it
  ```

- [ ] **Step 3 — run the test, expect FAIL (module missing).** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_contract_import.py -v
  ```
  Expected: FAIL with `ModuleNotFoundError: No module named 'scrapers.contract'`.

- [ ] **Step 4 — write `contract.py` verbatim from the canonical interface.** Write `/Users/jaehunb/projects/freemap/scrapers/contract.py`:
  ```python
  from dataclasses import dataclass, field
  from datetime import datetime


  @dataclass
  class RawDeal:
      source: str
      source_id: str
      title: str
      url: str
      description: str | None = None
      raw_location: str | None = None
      posted_at: datetime | None = None
      expires_at: datetime | None = None
      raw: dict = field(default_factory=dict)


  @dataclass
  class Deal:
      source: str
      source_id: str
      title: str
      url: str
      description: str | None
      deal_type: str        # "free" | "bogo" | "other"
      category: str         # "food" | "retail" | "event" | "other"
      placement: str        # "physical" | "online"
      lat: float | None
      lng: float | None
      raw_location: str | None
      geocode_status: str   # "ok" | "failed" | "n/a" | "pending"
      posted_at: datetime | None
      expires_at: datetime | None
      dedup_key: str | None = None
  ```

- [ ] **Step 5 — run the test, expect PASS.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_contract_import.py -v
  ```
  Expected: PASS, 3 passed.

- [ ] **Step 6 — commit.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add scrapers/__init__.py scrapers/contract.py tests/test_contract_import.py && git commit -m "feat(contract): add RawDeal and Deal dataclasses with import test"
  ```
  Expected: one commit listing 3 files.

### Task 1.3: Create `config.toml` and the canonical flat `Config` + `load_config()`

**Files:** `/Users/jaehunb/projects/freemap/config.toml`, `/Users/jaehunb/projects/freemap/scrapers/config.py`, `/Users/jaehunb/projects/freemap/tests/test_config.py`

- [ ] **Step 1 — create `config.toml`** with `[meta]`, `[freshness]`, `[geocoder]`, and `[sources]` tables that map onto the flat `Config` fields. Write `/Users/jaehunb/projects/freemap/config.toml`:
  ```toml
  [meta]
  metro = "seattle"
  db_path = "db/deals.db"
  user_agent = "FreeMapSeattle/1.0 (contact: freemap@example.com)"
  sources_enabled = ["reddit", "chains", "slickdeals", "local"]

  [freshness]
  stale_after_hours = 24

  [geocoder]
  min_interval_seconds = 1.0
  max_live_calls = 200

  [sources.reddit]
  subreddits = ["Seattle", "SeattleWA"]
  listing_urls = ["https://www.reddit.com/r/Seattle/search.json?q=free&restrict_sr=1"]

  [sources.chains]
  offers_urls = ["https://example-chain.com/offers"]

  [sources.chains.branches]
  "Capitol Hill" = "1429 12th Ave, Seattle, WA"

  [sources.slickdeals]
  listing_urls = ["https://slickdeals.net/local/seattle/"]

  [sources.local]
  feed_urls = ["https://example-local.com/deals.xml"]
  ```

- [ ] **Step 2 — write the failing config test FIRST.** Write `/Users/jaehunb/projects/freemap/tests/test_config.py`:
  ```python
  from scrapers.config import Config, load_config


  def test_load_config_reads_all_canonical_fields(tmp_path):
      cfg_text = """
  [meta]
  metro = "seattle"
  db_path = "db/deals.db"
  user_agent = "FreeMapSeattle/1.0 (contact: freemap@example.com)"
  sources_enabled = ["reddit", "chains", "slickdeals", "local"]

  [freshness]
  stale_after_hours = 24

  [geocoder]
  min_interval_seconds = 1.0
  max_live_calls = 200

  [sources.reddit]
  subreddits = ["Seattle", "SeattleWA"]
  listing_urls = ["https://www.reddit.com/r/Seattle/search.json"]
  """
      p = tmp_path / "config.toml"
      p.write_text(cfg_text)

      cfg = load_config(str(p))

      assert isinstance(cfg, Config)
      assert cfg.metro == "seattle"
      assert cfg.db_path == "db/deals.db"
      assert cfg.stale_after_hours == 24
      assert cfg.user_agent == "FreeMapSeattle/1.0 (contact: freemap@example.com)"
      assert cfg.geocoder_min_interval_seconds == 1.0
      assert cfg.geocoder_max_live_calls == 200
      assert cfg.sources_enabled == ["reddit", "chains", "slickdeals", "local"]
      # per-source settings reachable as a plain dict (NEVER via .get on Config)
      assert cfg.sources["reddit"]["subreddits"] == ["Seattle", "SeattleWA"]


  def test_load_config_applies_defaults_when_tables_absent(tmp_path):
      # Only [meta]; freshness/geocoder/sources omitted -> defaults fill in.
      p = tmp_path / "config.toml"
      p.write_text(
          '[meta]\n'
          'metro = "seattle"\n'
      )

      cfg = load_config(str(p))

      assert cfg.metro == "seattle"
      assert cfg.db_path == "db/deals.db"
      assert cfg.stale_after_hours == 24
      assert cfg.user_agent  # non-empty default User-Agent
      assert cfg.geocoder_min_interval_seconds == 1.0
      assert cfg.geocoder_max_live_calls == 200
      assert cfg.sources_enabled == ["reddit", "chains", "slickdeals", "local"]
      assert cfg.sources == {}


  def test_committed_config_toml_loads_and_reddit_reachable():
      # The real committed config at repo root must load and expose sources["reddit"].
      cfg = load_config("config.toml")
      assert cfg.metro == "seattle"
      assert "reddit" in cfg.sources_enabled
      assert cfg.sources["reddit"]["subreddits"]  # reachable, non-empty
  ```

- [ ] **Step 3 — run the test, expect FAIL (module missing).** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_config.py -v
  ```
  Expected: FAIL with `ModuleNotFoundError: No module named 'scrapers.config'`.

- [ ] **Step 4 — write `config.py` with the canonical flat `Config` and `load_config()`.** Note `tomllib.load` requires a binary file handle (`'rb'`). Write `/Users/jaehunb/projects/freemap/scrapers/config.py`:
  ```python
  import tomllib
  from dataclasses import dataclass, field

  # Default User-Agent used for ALL outbound requests (incl. Nominatim) when the
  # config omits [meta].user_agent. Nominatim policy requires an identifying UA.
  DEFAULT_USER_AGENT = "FreeMapSeattle/1.0 (contact: freemap@example.com)"


  @dataclass
  class Config:
      metro: str                                  # "seattle"
      db_path: str                                # "db/deals.db"
      stale_after_hours: int                      # 24
      user_agent: str                             # HTTP User-Agent for ALL outbound requests incl. Nominatim
      geocoder_min_interval_seconds: float        # 1.0
      geocoder_max_live_calls: int                # 200
      sources_enabled: list[str]                  # ["reddit", "chains", "slickdeals", "local"]
      sources: dict = field(default_factory=dict) # per-source settings


  def load_config(path: str = "config.toml") -> Config:
      """Parse a TOML config file into the flat Config dataclass.

      Maps the [meta]/[freshness]/[geocoder]/[sources] tables onto the flat
      fields and fills in defaults for anything omitted. Reads in binary mode
      because tomllib.load requires a file opened with 'rb'.
      """
      with open(path, "rb") as f:
          data = tomllib.load(f)

      meta = data.get("meta", {})
      freshness = data.get("freshness", {})
      geocoder = data.get("geocoder", {})
      sources = data.get("sources", {})

      return Config(
          metro=meta.get("metro", "seattle"),
          db_path=meta.get("db_path", "db/deals.db"),
          stale_after_hours=freshness.get("stale_after_hours", 24),
          user_agent=meta.get("user_agent", DEFAULT_USER_AGENT),
          geocoder_min_interval_seconds=geocoder.get("min_interval_seconds", 1.0),
          geocoder_max_live_calls=geocoder.get("max_live_calls", 200),
          sources_enabled=meta.get(
              "sources_enabled", ["reddit", "chains", "slickdeals", "local"]
          ),
          sources=sources,
      )
  ```
  Note: `.get(...)` here is called on the **plain dicts returned by `tomllib`**, never on the `Config` dataclass. Consumers MUST read `config.metro`, `config.user_agent`, `config.sources[<name>]`, etc. as attributes.

- [ ] **Step 5 — run the test, expect PASS.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_config.py -v
  ```
  Expected: PASS, 3 passed.

- [ ] **Step 6 — commit.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add config.toml scrapers/config.py tests/test_config.py && git commit -m "feat(config): add flat Config dataclass, load_config (tomllib), and config.toml"
  ```
  Expected: one commit listing 3 files.

### Task 1.4: Create `db/schema.sql` with the three tables

**Files:** `/Users/jaehunb/projects/freemap/db/schema.sql`

- [ ] **Step 1 — create the `db/` directory.** Run:
  ```bash
  mkdir -p /Users/jaehunb/projects/freemap/db
  ```
  Expected: no output (directory created). The generated `db/deals.db` is gitignored (Task 1.1); `db/schema.sql` is committed.

- [ ] **Step 2 — write the schema.** It defines `deals` (with `UNIQUE(source, source_id)` and an index on `dedup_key`), `geocode_cache`, and `scrape_runs`, matching spec §3. Write `/Users/jaehunb/projects/freemap/db/schema.sql`:
  ```sql
  -- FreeMap Seattle schema. Executed by scrapers.db.init_db().
  -- The generated db/deals.db is gitignored; this file is the committed source of truth.

  CREATE TABLE IF NOT EXISTS deals (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      source          TEXT NOT NULL,
      source_id       TEXT NOT NULL,
      dedup_key       TEXT,
      title           TEXT NOT NULL,
      url             TEXT NOT NULL,
      description     TEXT,
      deal_type       TEXT NOT NULL,   -- "free" | "bogo" | "other"
      category        TEXT NOT NULL,   -- "food" | "retail" | "event" | "other"
      placement       TEXT NOT NULL,   -- "physical" | "online"
      lat             REAL,
      lng             REAL,
      raw_location    TEXT,
      geocode_status  TEXT NOT NULL,   -- "ok" | "failed" | "n/a" | "pending"
      posted_at       TIMESTAMP,
      expires_at      TIMESTAMP,
      first_seen      TIMESTAMP,
      last_seen       TIMESTAMP,       -- stamped every scrape run — freshness core
      status          TEXT NOT NULL DEFAULT 'active',  -- seeded default; live freshness recomputed at read via compute_status()
      UNIQUE(source, source_id)
  );

  CREATE INDEX IF NOT EXISTS idx_deals_dedup_key ON deals(dedup_key);

  CREATE TABLE IF NOT EXISTS geocode_cache (
      raw_location    TEXT PRIMARY KEY,
      lat             REAL,
      lng             REAL,
      status          TEXT             -- "ok" | "failed"
  );

  CREATE TABLE IF NOT EXISTS scrape_runs (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      source          TEXT NOT NULL,
      started_at      TIMESTAMP,
      finished_at     TIMESTAMP,
      deals_found     INTEGER,
      errors          TEXT
  );
  ```
  Note: `status` is stored (spec §3) with a default of `'active'` so writers can populate it, but the **authoritative** freshness shown to users is recomputed at read time by `compute_status(expires_at, last_seen, now, stale_after_hours)` in the API (Milestone 4). The stored column is a convenience/seed value, never the source of truth for stale/expired display.

- [ ] **Step 3 — sanity-check the SQL parses** by loading it into a throwaway in-memory DB. Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.executescript(open('db/schema.sql').read()); print(sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")))"
  ```
  Expected: `['deals', 'geocode_cache', 'scrape_runs']`.

- [ ] **Step 4 — commit.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add db/schema.sql && git commit -m "feat(db): add schema.sql (deals, geocode_cache, scrape_runs)"
  ```
  Expected: one commit listing 1 file.

### Task 1.5: Add `tests/conftest.py` with an in-memory DB fixture

**Files:** `/Users/jaehunb/projects/freemap/tests/conftest.py`

- [ ] **Step 1 — write `conftest.py`** providing a `conn` fixture: an in-memory SQLite connection with `row_factory = sqlite3.Row`, the schema already applied via `executescript`, and a fixed `NOW` for deterministic freshness tests later. The fixture reads `db/schema.sql` relative to the repo root so it stays in sync with the committed schema. Write `/Users/jaehunb/projects/freemap/tests/conftest.py`:
  ```python
  import sqlite3
  from datetime import datetime
  from pathlib import Path

  import pytest

  # Repo root = parent of the tests/ directory.
  REPO_ROOT = Path(__file__).resolve().parent.parent
  SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

  # Fixed clock for deterministic freshness assertions across the whole suite.
  NOW = datetime(2026, 6, 18, 12, 0, 0)


  @pytest.fixture
  def now():
      """A fixed 'now' so freshness tests never depend on the wall clock."""
      return NOW


  @pytest.fixture
  def conn():
      """In-memory SQLite connection with the committed schema applied.

      row_factory = sqlite3.Row so rows are accessible by column name, matching
      what scrapers.db.connect() produces.
      """
      connection = sqlite3.connect(":memory:")
      connection.row_factory = sqlite3.Row
      connection.executescript(SCHEMA_PATH.read_text())
      yield connection
      connection.close()
  ```

- [ ] **Step 2 — verify the fixture is collectible** (no test asserts yet; just confirm pytest imports `conftest.py` without error). Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest --collect-only -q
  ```
  Expected: collection succeeds (lists the existing contract/config tests), no errors importing `conftest.py`.

- [ ] **Step 3 — commit.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add tests/conftest.py && git commit -m "test: add in-memory DB + fixed-now pytest fixtures"
  ```
  Expected: one commit listing 1 file.

### Task 1.6: Implement `scrapers/db.py` — connect, init_db, record_run, upsert_deals (REAL); fetch_all_deals stub

**Files:** `/Users/jaehunb/projects/freemap/scrapers/db.py`, `/Users/jaehunb/projects/freemap/tests/test_db_schema.py`

- [ ] **Step 1 — write the failing schema/db test FIRST.** This drives `init_db` (creates all 3 tables), `connect` (row_factory), `record_run`, and `upsert_deals` (insert + re-upsert bumps `last_seen`, preserves `first_seen`). It also asserts `fetch_all_deals` is a NotImplementedError stub for now. Write `/Users/jaehunb/projects/freemap/tests/test_db_schema.py`:
  ```python
  import sqlite3
  from datetime import datetime

  import pytest

  from scrapers.contract import Deal
  from scrapers import db


  def _deal(source_id="r1", title="Free coffee"):
      return Deal(
          source="reddit",
          source_id=source_id,
          title=title,
          url="http://x",
          description=None,
          deal_type="free",
          category="food",
          placement="physical",
          lat=47.6,
          lng=-122.3,
          raw_location="Capitol Hill",
          geocode_status="ok",
          posted_at=None,
          expires_at=None,
          dedup_key="k1",
      )


  def test_connect_uses_row_factory(tmp_path):
      conn = db.connect(str(tmp_path / "t.db"))
      assert conn.row_factory is sqlite3.Row
      conn.close()


  def test_init_db_creates_all_three_tables(conn):
      # conn fixture already ran the schema, but init_db must be idempotent and
      # also create the tables on a fresh connection.
      fresh = sqlite3.connect(":memory:")
      fresh.row_factory = sqlite3.Row
      db.init_db(fresh)
      names = sorted(r[0] for r in fresh.execute(
          "SELECT name FROM sqlite_master WHERE type='table'"
      ))
      assert names == ["deals", "geocode_cache", "scrape_runs"]
      fresh.close()


  def test_init_db_is_idempotent(conn):
      db.init_db(conn)  # schema already applied by fixture; must not raise
      db.init_db(conn)


  def test_upsert_inserts_then_bumps_last_seen(conn):
      t1 = datetime(2026, 6, 18, 10, 0, 0)
      t2 = datetime(2026, 6, 18, 11, 0, 0)

      n1 = db.upsert_deals(conn, [_deal()], t1)
      assert n1 == 1
      row = conn.execute("SELECT * FROM deals WHERE source_id='r1'").fetchone()
      assert row["first_seen"] == t1.isoformat()
      assert row["last_seen"] == t1.isoformat()

      # Re-upsert same (source, source_id): updates, does NOT duplicate.
      n2 = db.upsert_deals(conn, [_deal()], t2)
      assert n2 == 1
      rows = conn.execute("SELECT * FROM deals WHERE source_id='r1'").fetchall()
      assert len(rows) == 1
      assert rows[0]["first_seen"] == t1.isoformat()   # preserved
      assert rows[0]["last_seen"] == t2.isoformat()    # bumped


  def test_record_run_writes_one_row(conn):
      started = datetime(2026, 6, 18, 10, 0, 0)
      finished = datetime(2026, 6, 18, 10, 0, 5)
      db.record_run(conn, "reddit", started, finished, 3, None)
      row = conn.execute("SELECT * FROM scrape_runs").fetchone()
      assert row["source"] == "reddit"
      assert row["deals_found"] == 3
      assert row["errors"] is None


  def test_fetch_all_deals_is_stub_until_milestone_2(conn):
      with pytest.raises(NotImplementedError):
          db.fetch_all_deals(conn)
  ```

- [ ] **Step 2 — run the test, expect FAIL (module missing).** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_db_schema.py -v
  ```
  Expected: FAIL with `ModuleNotFoundError: No module named 'scrapers.db'`.

- [ ] **Step 3 — write `db.py`.** `connect`, `init_db`, `record_run`, and `upsert_deals` are REAL. `fetch_all_deals` is an explicit `NotImplementedError` stub that Milestone 2 replaces. Write `/Users/jaehunb/projects/freemap/scrapers/db.py`:
  ```python
  import sqlite3
  from datetime import datetime
  from pathlib import Path

  from scrapers.contract import Deal

  # Resolve schema.sql relative to this file so init_db works from any CWD.
  _SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


  def connect(path: str) -> sqlite3.Connection:
      """Open a SQLite connection with row_factory = sqlite3.Row."""
      conn = sqlite3.connect(path)
      conn.row_factory = sqlite3.Row
      return conn


  def init_db(conn: sqlite3.Connection) -> None:
      """Execute db/schema.sql against conn. Idempotent (schema uses IF NOT EXISTS)."""
      conn.executescript(_SCHEMA_PATH.read_text())
      conn.commit()


  def _to_db(value):
      """Serialize datetimes to ISO strings for SQLite; pass everything else through."""
      if isinstance(value, datetime):
          return value.isoformat()
      return value


  def upsert_deals(conn: sqlite3.Connection, deals: list[Deal], now: datetime) -> int:
      """Insert or update each deal on UNIQUE(source, source_id).

      On insert: first_seen and last_seen = now.
      On conflict: update mutable fields and bump last_seen = now; first_seen preserved.
      Per-row try/except so one bad row never aborts the batch. Returns rows upserted.
      """
      now_iso = now.isoformat()
      upserted = 0
      sql = """
          INSERT INTO deals (
              source, source_id, dedup_key, title, url, description,
              deal_type, category, placement, lat, lng, raw_location,
              geocode_status, posted_at, expires_at, first_seen, last_seen
          ) VALUES (
              :source, :source_id, :dedup_key, :title, :url, :description,
              :deal_type, :category, :placement, :lat, :lng, :raw_location,
              :geocode_status, :posted_at, :expires_at, :now, :now
          )
          ON CONFLICT(source, source_id) DO UPDATE SET
              dedup_key      = excluded.dedup_key,
              title          = excluded.title,
              url            = excluded.url,
              description    = excluded.description,
              deal_type      = excluded.deal_type,
              category       = excluded.category,
              placement      = excluded.placement,
              lat            = excluded.lat,
              lng            = excluded.lng,
              raw_location   = excluded.raw_location,
              geocode_status = excluded.geocode_status,
              posted_at      = excluded.posted_at,
              expires_at     = excluded.expires_at,
              last_seen      = :now
      """
      for deal in deals:
          params = {
              "source": deal.source,
              "source_id": deal.source_id,
              "dedup_key": deal.dedup_key,
              "title": deal.title,
              "url": deal.url,
              "description": deal.description,
              "deal_type": deal.deal_type,
              "category": deal.category,
              "placement": deal.placement,
              "lat": deal.lat,
              "lng": deal.lng,
              "raw_location": deal.raw_location,
              "geocode_status": deal.geocode_status,
              "posted_at": _to_db(deal.posted_at),
              "expires_at": _to_db(deal.expires_at),
              "now": now_iso,
          }
          try:
              conn.execute(sql, params)
              upserted += 1
          except sqlite3.Error:
              # One bad row never aborts the batch.
              continue
      conn.commit()
      return upserted


  def record_run(
      conn: sqlite3.Connection,
      source: str,
      started_at,
      finished_at,
      deals_found: int,
      errors: str | None,
  ) -> None:
      """Write one row to scrape_runs for a single source's run."""
      conn.execute(
          """
          INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors)
          VALUES (?, ?, ?, ?, ?)
          """,
          (source, _to_db(started_at), _to_db(finished_at), deals_found, errors),
      )
      conn.commit()


  def fetch_all_deals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
      """SELECT * FROM deals.

      STUB ONLY — replaced with a real, test-first implementation in Milestone 2.
      Present now so the package imports cleanly. Must NOT remain NotImplementedError
      after Milestone 2.
      """
      raise NotImplementedError("fetch_all_deals is implemented in Milestone 2")
  ```

- [ ] **Step 4 — run the test, expect PASS.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_db_schema.py -v
  ```
  Expected: PASS, 7 passed.

- [ ] **Step 5 — commit.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add scrapers/db.py tests/test_db_schema.py && git commit -m "feat(db): connect/init_db/upsert_deals/record_run real; fetch_all_deals stub for M2"
  ```
  Expected: one commit listing 2 files.

### Task 1.7: Create `scrapers/pipeline.py` with stage signatures present and `run_pipeline` documented stub

**Files:** `/Users/jaehunb/projects/freemap/scrapers/pipeline.py`, `/Users/jaehunb/projects/freemap/tests/test_pipeline_skeleton.py`

- [ ] **Step 1 — write the failing skeleton test FIRST.** It asserts every canonical pipeline name is importable and has the right signature, and that `run_pipeline` is still a `NotImplementedError` stub at this milestone. Write `/Users/jaehunb/projects/freemap/tests/test_pipeline_skeleton.py`:
  ```python
  import inspect

  import pytest

  from scrapers import pipeline


  def test_all_stage_functions_exist():
      for name in ("normalize", "classify", "geocode_deal", "dedup",
                   "compute_status", "run_pipeline"):
          assert hasattr(pipeline, name), f"missing pipeline.{name}"
          assert callable(getattr(pipeline, name))


  def test_run_pipeline_signature_is_canonical():
      sig = inspect.signature(pipeline.run_pipeline)
      assert list(sig.parameters) == ["raws", "geocoder", "conn", "now"]


  def test_compute_status_signature_is_canonical():
      sig = inspect.signature(pipeline.compute_status)
      assert list(sig.parameters) == [
          "expires_at", "last_seen", "now", "stale_after_hours"
      ]


  def test_run_pipeline_is_stub_until_milestone_2():
      with pytest.raises(NotImplementedError):
          pipeline.run_pipeline([], geocoder=None, conn=None, now=None)
  ```

- [ ] **Step 2 — run the test, expect FAIL (module missing).** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_pipeline_skeleton.py -v
  ```
  Expected: FAIL with `ModuleNotFoundError: No module named 'scrapers.pipeline'`.

- [ ] **Step 3 — write `pipeline.py`** with all stage functions present. `normalize`, `classify`, `geocode_deal`, `dedup`, and `compute_status` get real bodies implemented and TDD-verified in Milestone 2; here they carry the canonical signatures and a `NotImplementedError` body. `run_pipeline` is the explicitly documented stub Milestone 2 replaces. Write `/Users/jaehunb/projects/freemap/scrapers/pipeline.py`:
  ```python
  from datetime import datetime

  from scrapers.contract import RawDeal, Deal


  def normalize(raw: RawDeal) -> RawDeal:
      """Strip/collapse whitespace in title/description; defensive date pass; never raises.

      STUB — implemented test-first in Milestone 2.
      """
      raise NotImplementedError("normalize is implemented in Milestone 2")


  def classify(raw: RawDeal) -> Deal:
      """Derive deal_type, placement, category; lat=lng=None;
      geocode_status="n/a" if online else "pending".

      STUB — implemented test-first in Milestone 2.
      """
      raise NotImplementedError("classify is implemented in Milestone 2")


  def geocode_deal(deal: Deal, geocoder) -> Deal:
      """If placement=="physical" and geocode_status=="pending":
      geocoder.geocode(raw_location) -> set lat/lng + status "ok"/"failed";
      else unchanged.

      STUB — implemented test-first in Milestone 2.
      """
      raise NotImplementedError("geocode_deal is implemented in Milestone 2")


  def dedup(deals: list[Deal]) -> list[Deal]:
      """Set .dedup_key on each (normalized hash of merchant/title + location +
      deal_type); does NOT remove rows (API collapses on read).

      STUB — implemented test-first in Milestone 2.
      """
      raise NotImplementedError("dedup is implemented in Milestone 2")


  def compute_status(expires_at, last_seen, now, stale_after_hours: int) -> str:
      """Pure function -> "expired" | "stale" | "active".

      expired if expires_at and expires_at < now;
      stale if (now - last_seen) > stale_after_hours hours; else active.

      STUB — implemented test-first in Milestone 2.
      """
      raise NotImplementedError("compute_status is implemented in Milestone 2")


  def run_pipeline(raws: list[RawDeal], geocoder, conn, now) -> int:
      """For each raw: try/except (one bad row never aborts the batch) ->
      normalize -> classify -> geocode_deal; collect; dedup; upsert_deals; return count.

      STUB ONLY — FULLY IMPLEMENTED (NOT a stub) in Milestone 2. Present now so the
      package imports cleanly. Must NOT remain NotImplementedError after Milestone 2.
      """
      raise NotImplementedError("run_pipeline is implemented in Milestone 2")
  ```

- [ ] **Step 4 — run the test, expect PASS.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_pipeline_skeleton.py -v
  ```
  Expected: PASS, 4 passed.

- [ ] **Step 5 — commit.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add scrapers/pipeline.py tests/test_pipeline_skeleton.py && git commit -m "feat(pipeline): add canonical stage signatures; run_pipeline documented stub for M2"
  ```
  Expected: one commit listing 2 files.

### Task 1.8: Verify the whole skeleton is green and the package imports cleanly

**Files:** (no new files — verification only)

- [ ] **Step 1 — run the full suite.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest -v
  ```
  Expected: PASS, all tests across `test_contract_import.py`, `test_config.py`, `test_db_schema.py`, `test_pipeline_skeleton.py` green (no failures, no errors).

- [ ] **Step 2 — confirm the package imports cleanly with no side effects.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -c "import scrapers, scrapers.contract, scrapers.config, scrapers.db, scrapers.pipeline; from scrapers.contract import RawDeal, Deal; from scrapers.config import Config, load_config; print('imports OK')"
  ```
  Expected: prints `imports OK` with no traceback.

- [ ] **Step 3 — confirm the schema creates all three tables end-to-end via `db.init_db`.** Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -c "import sqlite3; from scrapers import db; c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row; db.init_db(c); print(sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")))"
  ```
  Expected: `['deals', 'geocode_cache', 'scrape_runs']`.

- [ ] **Step 4 — confirm Config exposes all canonical fields** from the committed `config.toml`. Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -c "from scrapers.config import load_config; c=load_config('config.toml'); print(c.metro, c.db_path, c.stale_after_hours, c.geocoder_min_interval_seconds, c.geocoder_max_live_calls, c.sources_enabled); print(c.sources['reddit'])"
  ```
  Expected: prints the values (`seattle db/deals.db 24 1.0 200 ['reddit', 'chains', 'slickdeals', 'local']`) followed by the reddit sub-dict.

- [ ] **Step 5 — confirm the two M2-owned stubs are still NotImplementedError** (so the Milestone 2 hand-off is unambiguous). Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && python -c "
  from scrapers import db, pipeline
  import sqlite3
  c = sqlite3.connect(':memory:'); db.init_db(c)
  for label, fn in [('db.fetch_all_deals', lambda: db.fetch_all_deals(c)), ('pipeline.run_pipeline', lambda: pipeline.run_pipeline([], None, c, None))]:
      try:
          fn(); print(label, 'ERROR: not a stub')
      except NotImplementedError:
          print(label, 'stub OK (M2 replaces)')
  "
  ```
  Expected: `db.fetch_all_deals stub OK (M2 replaces)` and `pipeline.run_pipeline stub OK (M2 replaces)`.

- [ ] **Step 6 — final milestone commit** (records the green end state; no code changes, so use an allow-empty marker commit only if `git status` is clean, otherwise stage any stragglers). Run:
  ```bash
  cd /Users/jaehunb/projects/freemap && git add -A && git status --short && git commit -m "chore: verify Milestone 1 skeleton green (3 tables, Config fields, clean imports)" --allow-empty
  ```
  Expected: a commit is created; `git status --short` shows a clean tree afterward. Milestone 1 end state reached: pytest green, schema creates all 3 tables, `Config` exposes all canonical fields, contract dataclasses import cleanly. **Milestone 2 replaces the two NotImplementedError stubs (`db.fetch_all_deals`, `pipeline.run_pipeline`) plus the stage-function bodies (`normalize`, `classify`, `geocode_deal`, `dedup`, `compute_status`) with real, test-first implementations.**

---

I've read the spec. Now I'll draft Milestone 2 with full TDD discipline, exact paths, complete code, and frequent commits using the canonical interfaces verbatim.

## Milestone 2: Pipeline stages + run_pipeline + fetch_all_deals (TDD)

**Goal:** Test-first implement every pipeline stage (normalize, classify, geocode_deal, dedup, compute_status), real cache-first Geocoder, real upsert_deals/fetch_all_deals, and replace both M1 NotImplementedError stubs (run_pipeline, fetch_all_deals) with verified implementations — leaving all stage unit tests green and zero NotImplementedError in scrapers/.

### Task 2.1: Pin time in conftest + sanity-check the M1 import surface

**Files:** `tests/conftest.py`

- [ ] **Step 1 — Add a shared fixed-`now` fixture and an in-memory DB fixture to `tests/conftest.py`.** Open `tests/conftest.py` and ensure it contains exactly this (append the fixtures below if the file already has imports from M1; if the named fixtures already exist, leave them and skip):

```python
# tests/conftest.py
from datetime import datetime

import pytest

from scrapers.db import connect, init_db

# Canonical fixed "now" used across freshness/pipeline/API tests so assertions
# never depend on wall-clock time.
NOW = datetime(2026, 6, 18, 12, 0, 0)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def conn():
    """Fresh in-memory SQLite DB with the schema applied."""
    c = connect(":memory:")
    init_db(c)
    yield c
    c.close()
```

- [ ] **Step 2 — Confirm the package still imports (M1 stubs present).** Run: `cd /Users/jaehunb/projects/freemap && python -c "import scrapers.pipeline, scrapers.db, scrapers.geocode, scrapers.contract"`
  Expected: exits 0, no output. (M1 created `run_pipeline` and `fetch_all_deals` as `NotImplementedError` stubs; importing the module must NOT raise — only calling the stub raises.)

- [ ] **Step 3 — Confirm `connect(":memory:")` + `init_db` work via the new fixture.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/conftest.py -q` then a one-liner: `python -c "from scrapers.db import connect, init_db; c=connect(':memory:'); init_db(c); print(sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")))"`
  Expected: prints `['deals', 'geocode_cache', 'scrape_runs']` (sqlite_sequence may also appear; that is fine).

- [ ] **Step 4 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add tests/conftest.py && git commit -m "test(conftest): add fixed-now and in-memory conn fixtures for M2"
```

### Task 2.2: `normalize` — strip/collapse whitespace, defensive date pass

**Files:** `tests/test_normalize.py`, `scrapers/pipeline.py`

- [ ] **Step 1 — Write the failing test.** Create `tests/test_normalize.py` with full content:

```python
# tests/test_normalize.py
from datetime import datetime

from scrapers.contract import RawDeal
from scrapers.pipeline import normalize


def _raw(**kw):
    base = dict(source="reddit", source_id="abc", title="t", url="http://x")
    base.update(kw)
    return RawDeal(**base)


def test_normalize_collapses_internal_and_edge_whitespace():
    raw = _raw(title="  Free   Coffee\tat\nCafe  ", description="  hi   there ")
    out = normalize(raw)
    assert out.title == "Free Coffee at Cafe"
    assert out.description == "hi there"


def test_normalize_handles_none_description():
    raw = _raw(description=None)
    out = normalize(raw)
    assert out.description is None


def test_normalize_passes_through_valid_datetimes():
    posted = datetime(2026, 6, 1, 9, 0, 0)
    raw = _raw(posted_at=posted, expires_at=datetime(2026, 7, 1, 0, 0, 0))
    out = normalize(raw)
    assert out.posted_at == posted
    assert out.expires_at == datetime(2026, 7, 1, 0, 0, 0)


def test_normalize_coerces_bad_date_to_none_never_raises():
    raw = _raw(posted_at="not-a-date", expires_at=12345)  # type: ignore[arg-type]
    out = normalize(raw)
    assert out.posted_at is None
    assert out.expires_at is None
    assert out.title == "t"
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_normalize.py -v`
  Expected: FAIL. M1's `normalize` is a stub, so tests error/fail (e.g. `NotImplementedError` or assertion mismatch on whitespace).

- [ ] **Step 3 — Implement `normalize` in `scrapers/pipeline.py`.** Replace the M1 `normalize` stub with this exact function (keep the module's existing imports; ensure `from datetime import datetime` and `from scrapers.contract import RawDeal, Deal` are present at top):

```python
def normalize(raw: RawDeal) -> RawDeal:
    """Strip/collapse whitespace in title/description; defensive date pass.

    Never raises: a bad/non-datetime date becomes None.
    """
    def _clean(s: str | None) -> str | None:
        if s is None:
            return None
        return " ".join(s.split())

    def _safe_dt(v: object) -> datetime | None:
        return v if isinstance(v, datetime) else None

    raw.title = _clean(raw.title) or ""
    raw.description = _clean(raw.description)
    raw.raw_location = _clean(raw.raw_location)
    raw.posted_at = _safe_dt(raw.posted_at)
    raw.expires_at = _safe_dt(raw.expires_at)
    return raw
```

- [ ] **Step 4 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_normalize.py -v`
  Expected: PASS, 4 passed.

- [ ] **Step 5 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/pipeline.py tests/test_normalize.py && git commit -m "feat(pipeline): implement normalize stage (TDD)"
```

### Task 2.3: `classify` — deal_type / placement / category rules

**Files:** `tests/test_classify.py`, `scrapers/pipeline.py`

- [ ] **Step 1 — Write the failing test.** Create `tests/test_classify.py` with full content (covers BOGO vs free vs other, physical vs online, and each category):

```python
# tests/test_classify.py
from scrapers.contract import RawDeal
from scrapers.pipeline import classify


def _raw(title="t", description=None, raw_location=None):
    return RawDeal(
        source="reddit",
        source_id="abc",
        title=title,
        url="http://x",
        description=description,
        raw_location=raw_location,
    )


# ---- deal_type ----
def test_deal_type_free():
    assert classify(_raw(title="Free coffee today")).deal_type == "free"


def test_deal_type_bogo_overrides_free_via_buy_one():
    assert classify(_raw(title="Buy one get one free pizza")).deal_type == "bogo"


def test_deal_type_bogo_via_b1g1():
    assert classify(_raw(title="B1G1 burrito deal")).deal_type == "bogo"


def test_deal_type_other_via_percent_off():
    assert classify(_raw(title="50% off shoes")).deal_type == "other"


def test_deal_type_other_default():
    assert classify(_raw(title="Cool concert announcement")).deal_type == "other"


# ---- placement ----
def test_placement_physical_when_location_present():
    assert classify(_raw(raw_location="Capitol Hill")).placement == "physical"


def test_placement_online_when_no_location():
    d = classify(_raw(raw_location=None))
    assert d.placement == "online"
    assert d.geocode_status == "n/a"
    assert d.lat is None and d.lng is None


def test_physical_starts_pending_geocode():
    d = classify(_raw(raw_location="1429 12th Ave"))
    assert d.geocode_status == "pending"
    assert d.lat is None and d.lng is None


# ---- category ----
def test_category_food():
    assert classify(_raw(title="Free pizza and coffee")).category == "food"


def test_category_event():
    assert classify(_raw(title="Free concert festival")).category == "event"


def test_category_retail():
    assert classify(_raw(title="Free shoes at the store")).category == "retail"


def test_category_other():
    assert classify(_raw(title="Free advice")).category == "other"


# ---- field passthrough ----
def test_passes_through_identity_fields():
    d = classify(_raw(title="Free coffee", description="desc", raw_location="X"))
    assert d.source == "reddit"
    assert d.source_id == "abc"
    assert d.url == "http://x"
    assert d.description == "desc"
    assert d.raw_location == "X"
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_classify.py -v`
  Expected: FAIL (M1 `classify` stub).

- [ ] **Step 3 — Implement `classify` in `scrapers/pipeline.py`.** Replace the M1 `classify` stub with this exact function:

```python
def classify(raw: RawDeal) -> Deal:
    """Derive deal_type, placement, category from a (normalized) RawDeal.

    Ambiguous inputs fall back to safe defaults ("other"/"online").
    lat=lng=None always; geocode_status is "n/a" for online, "pending" for physical.
    """
    text = " ".join(p for p in (raw.title, raw.description) if p).lower()

    # deal_type: BOGO beats "free"; then discount-ish -> other; else other.
    if any(k in text for k in ("buy one", "bogo", "b1g1")):
        deal_type = "bogo"
    elif "free" in text:
        deal_type = "free"
    elif any(k in text for k in ("% off", "discount", "sale")):
        deal_type = "other"
    else:
        deal_type = "other"

    placement = "physical" if raw.raw_location else "online"

    if any(k in text for k in ("food", "coffee", "burrito", "pizza", "drink", "meal")):
        category = "food"
    elif any(k in text for k in ("event", "show", "concert", "festival")):
        category = "event"
    elif any(k in text for k in ("store", "retail", "clothing", "shoes")):
        category = "retail"
    else:
        category = "other"

    geocode_status = "pending" if placement == "physical" else "n/a"

    return Deal(
        source=raw.source,
        source_id=raw.source_id,
        title=raw.title,
        url=raw.url,
        description=raw.description,
        deal_type=deal_type,
        category=category,
        placement=placement,
        lat=None,
        lng=None,
        raw_location=raw.raw_location,
        geocode_status=geocode_status,
        posted_at=raw.posted_at,
        expires_at=raw.expires_at,
    )
```

- [ ] **Step 4 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_classify.py -v`
  Expected: PASS, 14 passed.

- [ ] **Step 5 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/pipeline.py tests/test_classify.py && git commit -m "feat(pipeline): implement classify stage rules (TDD)"
```

### Task 2.4: `FakeGeocoder` + `geocode_deal` stage

**Files:** `tests/test_geocode.py`, `scrapers/geocode.py`, `scrapers/pipeline.py`

- [ ] **Step 1 — Write the failing test for FakeGeocoder + geocode_deal.** Create `tests/test_geocode.py` with full content (the live-Geocoder cache test is added in Task 2.5):

```python
# tests/test_geocode.py
from scrapers.contract import Deal
from scrapers.geocode import FakeGeocoder
from scrapers.pipeline import geocode_deal


def _deal(placement, geocode_status, raw_location):
    return Deal(
        source="reddit",
        source_id="abc",
        title="t",
        url="http://x",
        description=None,
        deal_type="free",
        category="food",
        placement=placement,
        lat=None,
        lng=None,
        raw_location=raw_location,
        geocode_status=geocode_status,
        posted_at=None,
        expires_at=None,
    )


def test_fake_geocoder_returns_mapping_hit():
    g = FakeGeocoder({"Capitol Hill": (47.6, -122.3)})
    assert g.geocode("Capitol Hill") == (47.6, -122.3)


def test_fake_geocoder_returns_none_on_miss():
    g = FakeGeocoder({})
    assert g.geocode("Nowhere") is None


def test_geocode_deal_ok_sets_latlng_and_status():
    g = FakeGeocoder({"Capitol Hill": (47.6, -122.3)})
    out = geocode_deal(_deal("physical", "pending", "Capitol Hill"), g)
    assert out.lat == 47.6
    assert out.lng == -122.3
    assert out.geocode_status == "ok"


def test_geocode_deal_failed_keeps_deal_nulls_status_failed():
    g = FakeGeocoder({})  # miss -> None
    out = geocode_deal(_deal("physical", "pending", "Unknown Place"), g)
    assert out.lat is None and out.lng is None
    assert out.geocode_status == "failed"


def test_geocode_deal_skips_online():
    g = FakeGeocoder({"X": (1.0, 2.0)})
    out = geocode_deal(_deal("online", "n/a", None), g)
    assert out.lat is None and out.lng is None
    assert out.geocode_status == "n/a"


def test_geocode_deal_skips_already_resolved_physical():
    g = FakeGeocoder({"X": (9.0, 9.0)})
    d = _deal("physical", "ok", "X")
    d.lat, d.lng = 1.0, 2.0
    out = geocode_deal(d, g)
    # status not "pending" -> unchanged
    assert out.lat == 1.0 and out.lng == 2.0
    assert out.geocode_status == "ok"
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_geocode.py -v`
  Expected: FAIL (M1 `geocode_deal` stub; `FakeGeocoder` may exist from M1 but is unverified).

- [ ] **Step 3 — Ensure `FakeGeocoder` exists in `scrapers/geocode.py`.** Confirm/replace the `FakeGeocoder` class to read exactly this (leave the `Geocoder` class as-is for now; Task 2.5 implements it):

```python
class FakeGeocoder:
    def __init__(self, mapping: dict[str, tuple[float, float]]):
        self.mapping = mapping

    def geocode(self, raw_location: str) -> tuple[float, float] | None:
        return self.mapping.get(raw_location)
```

- [ ] **Step 4 — Implement `geocode_deal` in `scrapers/pipeline.py`.** Replace the M1 `geocode_deal` stub with this exact function:

```python
def geocode_deal(deal: Deal, geocoder) -> Deal:
    """Resolve a physical deal's raw_location to lat/lng via the geocoder.

    Only acts when placement=="physical" and geocode_status=="pending".
    On hit -> set lat/lng + status "ok"; on miss -> leave NULL + status "failed".
    Online / already-resolved deals pass through unchanged.
    """
    if deal.placement == "physical" and deal.geocode_status == "pending":
        result = geocoder.geocode(deal.raw_location) if deal.raw_location else None
        if result is not None:
            deal.lat, deal.lng = result
            deal.geocode_status = "ok"
        else:
            deal.lat = None
            deal.lng = None
            deal.geocode_status = "failed"
    return deal
```

- [ ] **Step 5 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_geocode.py -v`
  Expected: PASS, 6 passed.

- [ ] **Step 6 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/geocode.py scrapers/pipeline.py tests/test_geocode.py && git commit -m "feat(pipeline): FakeGeocoder + geocode_deal stage (TDD)"
```

### Task 2.5: Real `Geocoder` — cache-first, live-only-on-miss, rate-cap

**Files:** `tests/test_geocode.py`, `scrapers/geocode.py`

- [ ] **Step 1 — Append the cache-first tests to `tests/test_geocode.py`.** Add this block to the end of `tests/test_geocode.py` (keeps the Task 2.4 tests intact):

```python
# ---- real Geocoder cache-first behavior ----
from scrapers.db import connect, init_db
from scrapers.geocode import Geocoder


def _conn():
    c = connect(":memory:")
    init_db(c)
    return c


def test_geocoder_cache_hit_no_live_call(monkeypatch):
    c = _conn()
    c.execute(
        "INSERT INTO geocode_cache(raw_location, lat, lng, status) VALUES (?,?,?,?)",
        ("Capitol Hill", 47.6, -122.3, "ok"),
    )
    c.commit()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)

    def _boom(*a, **k):
        raise AssertionError("live geocode must NOT be called on a cache hit")

    monkeypatch.setattr(g, "_live_geocode", _boom)
    assert g.geocode("Capitol Hill") == (47.6, -122.3)


def test_geocoder_cache_miss_calls_live_then_caches(monkeypatch):
    c = _conn()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)
    calls = []

    def _fake_live(loc):
        calls.append(loc)
        return (1.0, 2.0)

    monkeypatch.setattr(g, "_live_geocode", _fake_live)

    assert g.geocode("Fremont") == (1.0, 2.0)
    assert calls == ["Fremont"]

    # second call is served from cache -> no further live call
    assert g.geocode("Fremont") == (1.0, 2.0)
    assert calls == ["Fremont"]

    row = c.execute(
        "SELECT lat, lng, status FROM geocode_cache WHERE raw_location=?",
        ("Fremont",),
    ).fetchone()
    assert (row["lat"], row["lng"], row["status"]) == (1.0, 2.0, "ok")


def test_geocoder_cached_failure_returns_none_no_live_call(monkeypatch):
    c = _conn()
    c.execute(
        "INSERT INTO geocode_cache(raw_location, lat, lng, status) VALUES (?,?,?,?)",
        ("Bad Place", None, None, "failed"),
    )
    c.commit()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)
    monkeypatch.setattr(
        g, "_live_geocode", lambda loc: (_ for _ in ()).throw(AssertionError("no live"))
    )
    assert g.geocode("Bad Place") is None


def test_geocoder_live_miss_caches_failure(monkeypatch):
    c = _conn()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0)
    monkeypatch.setattr(g, "_live_geocode", lambda loc: None)
    assert g.geocode("Ghost Town") is None
    row = c.execute(
        "SELECT status FROM geocode_cache WHERE raw_location=?", ("Ghost Town",)
    ).fetchone()
    assert row["status"] == "failed"


def test_geocoder_respects_max_live_calls_cap(monkeypatch):
    c = _conn()
    g = Geocoder(c, user_agent="freemap-test", min_interval_seconds=0.0, max_live_calls=1)
    monkeypatch.setattr(g, "_live_geocode", lambda loc: (3.0, 4.0))
    assert g.geocode("LocA") == (3.0, 4.0)   # 1st live call allowed
    assert g.geocode("LocB") is None         # cap reached -> no live call, None
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_geocode.py -v`
  Expected: FAIL on the new cases (M1 `Geocoder` is a stub / lacks `_live_geocode` cache logic). The Task 2.4 tests still PASS.

- [ ] **Step 3 — Implement the real `Geocoder` in `scrapers/geocode.py`.** Replace the M1 `Geocoder` class with this exact implementation (top of file must have `import time`, `import httpx`):

```python
import time

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class Geocoder:
    def __init__(
        self,
        conn,
        user_agent: str,
        min_interval_seconds: float = 1.0,
        max_live_calls: int = 200,
    ):
        self.conn = conn
        self.user_agent = user_agent
        self.min_interval_seconds = min_interval_seconds
        self.max_live_calls = max_live_calls
        self._live_calls = 0
        self._last_call_at = 0.0

    def geocode(self, raw_location: str) -> tuple[float, float] | None:
        # 1) cache-first
        row = self.conn.execute(
            "SELECT lat, lng, status FROM geocode_cache WHERE raw_location = ?",
            (raw_location,),
        ).fetchone()
        if row is not None:
            if row["status"] == "ok":
                return (row["lat"], row["lng"])
            return None  # cached failure

        # 2) respect the per-run live-call cap
        if self._live_calls >= self.max_live_calls:
            return None

        # 3) polite rate limit between live calls
        if self.min_interval_seconds > 0:
            elapsed = time.monotonic() - self._last_call_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)

        self._live_calls += 1
        self._last_call_at = time.monotonic()
        result = self._live_geocode(raw_location)

        # 4) cache the outcome (success or failure) so we never re-hit it
        if result is not None:
            lat, lng = result
            self.conn.execute(
                "INSERT OR REPLACE INTO geocode_cache(raw_location, lat, lng, status) "
                "VALUES (?,?,?,?)",
                (raw_location, lat, lng, "ok"),
            )
        else:
            self.conn.execute(
                "INSERT OR REPLACE INTO geocode_cache(raw_location, lat, lng, status) "
                "VALUES (?,?,?,?)",
                (raw_location, None, None, "failed"),
            )
        self.conn.commit()
        return result

    def _live_geocode(self, raw_location: str) -> tuple[float, float] | None:
        """Single live Nominatim call. Tests monkeypatch this; never hit in tests."""
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": raw_location, "format": "json", "limit": 1},
            headers={"User-Agent": self.user_agent},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return (float(data[0]["lat"]), float(data[0]["lon"]))
```

- [ ] **Step 4 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_geocode.py -v`
  Expected: PASS, 11 passed (6 from Task 2.4 + 5 new).

- [ ] **Step 5 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/geocode.py tests/test_geocode.py && git commit -m "feat(geocode): cache-first rate-limited Geocoder (TDD)"
```

### Task 2.6: `dedup` — same deal across sources gets the same dedup_key

**Files:** `tests/test_dedup.py`, `scrapers/pipeline.py`

- [ ] **Step 1 — Write the failing test.** Create `tests/test_dedup.py` with full content:

```python
# tests/test_dedup.py
from scrapers.contract import Deal
from scrapers.pipeline import dedup


def _deal(source, source_id, title, raw_location, deal_type="free"):
    return Deal(
        source=source,
        source_id=source_id,
        title=title,
        url=f"http://{source}/{source_id}",
        description=None,
        deal_type=deal_type,
        category="food",
        placement="physical" if raw_location else "online",
        lat=None,
        lng=None,
        raw_location=raw_location,
        geocode_status="pending" if raw_location else "n/a",
        posted_at=None,
        expires_at=None,
    )


def test_dedup_assigns_key_to_every_deal():
    deals = [_deal("reddit", "1", "Free Coffee", "Capitol Hill")]
    out = dedup(deals)
    assert out[0].dedup_key is not None


def test_dedup_same_deal_across_sources_shares_key():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill")
    b = _deal("slickdeals", "99", "free   COFFEE", "capitol hill")  # whitespace/case differ
    out = dedup([a, b])
    assert out[0].dedup_key == out[1].dedup_key


def test_dedup_different_deal_type_differs():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill", deal_type="free")
    b = _deal("reddit", "2", "Free Coffee", "Capitol Hill", deal_type="bogo")
    out = dedup([a, b])
    assert out[0].dedup_key != out[1].dedup_key


def test_dedup_different_location_differs():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill")
    b = _deal("reddit", "2", "Free Coffee", "Fremont")
    out = dedup([a, b])
    assert out[0].dedup_key != out[1].dedup_key


def test_dedup_does_not_remove_rows():
    a = _deal("reddit", "1", "Free Coffee", "Capitol Hill")
    b = _deal("slickdeals", "99", "Free Coffee", "Capitol Hill")
    out = dedup([a, b])
    assert len(out) == 2  # collapse happens at API read, not here


def test_dedup_online_deal_uses_none_location_consistently():
    a = _deal("reddit", "1", "Free Ebook", None)
    b = _deal("slickdeals", "5", "free ebook", None)
    out = dedup([a, b])
    assert out[0].dedup_key == out[1].dedup_key
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_dedup.py -v`
  Expected: FAIL (M1 `dedup` stub).

- [ ] **Step 3 — Implement `dedup` in `scrapers/pipeline.py`.** Add `import hashlib` to the top of `scrapers/pipeline.py`, then replace the M1 `dedup` stub with this exact function:

```python
def dedup(deals: list[Deal]) -> list[Deal]:
    """Set .dedup_key on each deal (normalized hash of title+location+deal_type).

    Does NOT remove rows; the API collapses dedup_key groups on read.
    """
    def _norm(s: str | None) -> str:
        return " ".join(s.split()).lower() if s else ""

    for deal in deals:
        basis = "|".join((_norm(deal.title), _norm(deal.raw_location), deal.deal_type))
        deal.dedup_key = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return deals
```

- [ ] **Step 4 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_dedup.py -v`
  Expected: PASS, 6 passed.

- [ ] **Step 5 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/pipeline.py tests/test_dedup.py && git commit -m "feat(pipeline): implement dedup_key assignment (TDD)"
```

### Task 2.7: `compute_status` — expired / stale / active (pure)

**Files:** `tests/test_upsert_freshness.py`, `scrapers/pipeline.py`

- [ ] **Step 1 — Write the failing test (status portion).** Create `tests/test_upsert_freshness.py` with this content (the upsert tests are appended in Task 2.8):

```python
# tests/test_upsert_freshness.py
from datetime import datetime, timedelta

from scrapers.pipeline import compute_status

NOW = datetime(2026, 6, 18, 12, 0, 0)
STALE_HOURS = 24


def test_status_expired_when_expires_in_past():
    expires = NOW - timedelta(hours=1)
    last_seen = NOW  # fresh, but expiry wins
    assert compute_status(expires, last_seen, NOW, STALE_HOURS) == "expired"


def test_status_active_when_fresh_and_not_expired():
    expires = NOW + timedelta(days=7)
    last_seen = NOW - timedelta(hours=1)
    assert compute_status(expires, last_seen, NOW, STALE_HOURS) == "active"


def test_status_stale_when_last_seen_older_than_threshold():
    last_seen = NOW - timedelta(hours=25)  # > 24h
    assert compute_status(None, last_seen, NOW, STALE_HOURS) == "stale"


def test_status_active_at_exactly_threshold():
    last_seen = NOW - timedelta(hours=24)  # exactly 24h -> NOT > 24h -> active
    assert compute_status(None, last_seen, NOW, STALE_HOURS) == "active"


def test_status_none_expires_is_not_expired():
    last_seen = NOW - timedelta(hours=1)
    assert compute_status(None, last_seen, NOW, STALE_HOURS) == "active"


def test_status_expired_takes_priority_over_stale():
    expires = NOW - timedelta(hours=1)
    last_seen = NOW - timedelta(hours=100)  # also stale, but expired wins
    assert compute_status(expires, last_seen, NOW, STALE_HOURS) == "expired"
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_upsert_freshness.py -v`
  Expected: FAIL (M1 `compute_status` stub).

- [ ] **Step 3 — Implement `compute_status` in `scrapers/pipeline.py`.** Ensure `from datetime import datetime, timedelta` is at the top, then replace the M1 `compute_status` stub with this exact function:

```python
def compute_status(expires_at, last_seen, now, stale_after_hours: int) -> str:
    """Pure freshness function.

    "expired" if expires_at is set and in the past;
    else "stale" if (now - last_seen) > stale_after_hours hours;
    else "active".
    """
    if expires_at is not None and expires_at < now:
        return "expired"
    if last_seen is not None and (now - last_seen) > timedelta(hours=stale_after_hours):
        return "stale"
    return "active"
```

- [ ] **Step 4 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_upsert_freshness.py -v`
  Expected: PASS, 6 passed.

- [ ] **Step 5 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/pipeline.py tests/test_upsert_freshness.py && git commit -m "feat(pipeline): implement compute_status freshness (TDD)"
```

### Task 2.8: `upsert_deals` — insert new, re-upsert bumps last_seen, preserves first_seen

**Files:** `tests/test_upsert_freshness.py`, `scrapers/db.py`

- [ ] **Step 1 — Append the upsert tests to `tests/test_upsert_freshness.py`.** Add this block to the end of the file (uses the `conn` fixture from `tests/conftest.py`):

```python
# ---- upsert_deals behavior ----
from scrapers.contract import Deal
from scrapers.db import upsert_deals, fetch_all_deals


def _deal(source_id, title="Free Coffee"):
    return Deal(
        source="reddit",
        source_id=source_id,
        title=title,
        url="http://x",
        description=None,
        deal_type="free",
        category="food",
        placement="physical",
        lat=47.6,
        lng=-122.3,
        raw_location="Capitol Hill",
        geocode_status="ok",
        posted_at=None,
        expires_at=None,
        dedup_key="k1",
    )


def test_upsert_inserts_new_rows(conn):
    n = upsert_deals(conn, [_deal("a"), _deal("b")], NOW)
    assert n == 2
    rows = fetch_all_deals(conn)
    assert len(rows) == 2


def test_reupsert_same_source_id_does_not_duplicate(conn):
    upsert_deals(conn, [_deal("a")], NOW)
    upsert_deals(conn, [_deal("a", title="Free Coffee UPDATED")], NOW + timedelta(hours=5))
    rows = fetch_all_deals(conn)
    assert len(rows) == 1
    assert rows[0]["title"] == "Free Coffee UPDATED"


def test_reupsert_bumps_last_seen_preserves_first_seen(conn):
    later = NOW + timedelta(hours=5)
    upsert_deals(conn, [_deal("a")], NOW)
    first = fetch_all_deals(conn)[0]
    assert first["first_seen"] == NOW.isoformat()
    assert first["last_seen"] == NOW.isoformat()

    upsert_deals(conn, [_deal("a")], later)
    again = fetch_all_deals(conn)[0]
    assert again["first_seen"] == NOW.isoformat()       # preserved
    assert again["last_seen"] == later.isoformat()      # bumped


def test_upsert_one_bad_row_does_not_abort_batch(conn):
    bad = _deal("good1")
    bad.source = None  # NOT NULL violation -> per-row try/except must skip it
    n = upsert_deals(conn, [bad, _deal("good2")], NOW)
    rows = fetch_all_deals(conn)
    ids = sorted(r["source_id"] for r in rows)
    assert ids == ["good2"]
    assert n == 1
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_upsert_freshness.py -v`
  Expected: FAIL on the new upsert tests (M1 `upsert_deals` may be a partial stub; `fetch_all_deals` is still a `NotImplementedError` stub so all upsert tests error).

- [ ] **Step 3 — Implement `upsert_deals` in `scrapers/db.py`.** Ensure the top of `scrapers/db.py` has `import sqlite3` and `from datetime import datetime` and `from scrapers.contract import Deal`, then replace the M1 `upsert_deals` body with this exact function:

```python
def upsert_deals(conn, deals: list[Deal], now: datetime) -> int:
    """Insert or update each deal on UNIQUE(source, source_id).

    On conflict: update mutable fields + bump last_seen=:now; first_seen preserved.
    Per-row try/except so one bad row never aborts the batch. Returns rows upserted.
    """
    sql = """
        INSERT INTO deals (
            source, source_id, dedup_key, title, url, description,
            deal_type, category, placement, lat, lng, raw_location,
            geocode_status, posted_at, expires_at, first_seen, last_seen, status
        ) VALUES (
            :source, :source_id, :dedup_key, :title, :url, :description,
            :deal_type, :category, :placement, :lat, :lng, :raw_location,
            :geocode_status, :posted_at, :expires_at, :now, :now, 'active'
        )
        ON CONFLICT(source, source_id) DO UPDATE SET
            dedup_key=excluded.dedup_key,
            title=excluded.title,
            url=excluded.url,
            description=excluded.description,
            deal_type=excluded.deal_type,
            category=excluded.category,
            placement=excluded.placement,
            lat=excluded.lat,
            lng=excluded.lng,
            raw_location=excluded.raw_location,
            geocode_status=excluded.geocode_status,
            posted_at=excluded.posted_at,
            expires_at=excluded.expires_at,
            last_seen=:now
    """
    count = 0
    for d in deals:
        params = {
            "source": d.source,
            "source_id": d.source_id,
            "dedup_key": d.dedup_key,
            "title": d.title,
            "url": d.url,
            "description": d.description,
            "deal_type": d.deal_type,
            "category": d.category,
            "placement": d.placement,
            "lat": d.lat,
            "lng": d.lng,
            "raw_location": d.raw_location,
            "geocode_status": d.geocode_status,
            "posted_at": d.posted_at.isoformat() if d.posted_at else None,
            "expires_at": d.expires_at.isoformat() if d.expires_at else None,
            "now": now.isoformat(),
        }
        try:
            conn.execute(sql, params)
            count += 1
        except sqlite3.Error:
            continue
    conn.commit()
    return count
```

- [ ] **Step 4 — Implement `fetch_all_deals` (replaces the M1 stub).** Replace the M1 `fetch_all_deals` `NotImplementedError` stub in `scrapers/db.py` with this exact function:

```python
def fetch_all_deals(conn) -> list:
    """Return all deal rows (sqlite3.Row objects). FULLY IMPLEMENTED (not a stub)."""
    return conn.execute("SELECT * FROM deals").fetchall()
```

- [ ] **Step 5 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_upsert_freshness.py -v`
  Expected: PASS, 10 passed (6 status + 4 upsert).

- [ ] **Step 6 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/db.py tests/test_upsert_freshness.py && git commit -m "feat(db): implement upsert_deals + fetch_all_deals (TDD)"
```

### Task 2.9: `run_pipeline` — full per-row try/except chain, replaces M1 stub

**Files:** `tests/test_pipeline_integration.py`, `scrapers/pipeline.py`

- [ ] **Step 1 — Write the failing integration test.** Create `tests/test_pipeline_integration.py` with full content (uses the `conn` and `now` fixtures from `tests/conftest.py`):

```python
# tests/test_pipeline_integration.py
from scrapers.contract import RawDeal
from scrapers.db import fetch_all_deals
from scrapers.geocode import FakeGeocoder
from scrapers.pipeline import run_pipeline


def _raw(source_id, title, raw_location=None):
    return RawDeal(
        source="reddit",
        source_id=source_id,
        title=title,
        url=f"http://x/{source_id}",
        raw_location=raw_location,
    )


def test_run_pipeline_end_to_end_inserts_rows(conn, now):
    geocoder = FakeGeocoder({"Capitol Hill": (47.6, -122.3)})
    raws = [
        _raw("1", "Free coffee", "Capitol Hill"),   # physical, geocodes ok
        _raw("2", "Free ebook download"),            # online
        _raw("3", "Buy one get one free pizza", "Unknown Place"),  # geocode fails
    ]
    n = run_pipeline(raws, geocoder, conn, now)
    assert n == 3
    rows = {r["source_id"]: r for r in fetch_all_deals(conn)}
    assert len(rows) == 3
    assert rows["1"]["geocode_status"] == "ok"
    assert rows["1"]["placement"] == "physical"
    assert rows["2"]["placement"] == "online"
    assert rows["2"]["geocode_status"] == "n/a"
    assert rows["3"]["deal_type"] == "bogo"
    assert rows["3"]["geocode_status"] == "failed"
    # every row got a dedup_key
    assert all(rows[k]["dedup_key"] for k in rows)


def test_run_pipeline_one_malformed_raw_does_not_abort_batch(conn, now):
    geocoder = FakeGeocoder({})

    class Exploding(RawDeal):
        @property
        def title(self):  # blows up inside normalize when accessed
            raise ValueError("boom")

        @title.setter
        def title(self, v):
            pass

    bad = Exploding(source="reddit", source_id="bad", title="x", url="http://x")
    good = _raw("ok", "Free coffee")
    n = run_pipeline([bad, good], geocoder, conn, now)
    rows = [r["source_id"] for r in fetch_all_deals(conn)]
    assert rows == ["ok"]   # bad row skipped, batch survived
    assert n == 1


def test_run_pipeline_returns_zero_for_empty_input(conn, now):
    assert run_pipeline([], FakeGeocoder({}), conn, now) == 0
```

- [ ] **Step 2 — Run it, expect FAIL.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_pipeline_integration.py -v`
  Expected: FAIL — calling the M1 `run_pipeline` stub raises `NotImplementedError`.

- [ ] **Step 3 — Implement `run_pipeline` in `scrapers/pipeline.py` (replaces the M1 stub).** Ensure `from scrapers.db import upsert_deals` is imported at the top of `scrapers/pipeline.py`, then replace the M1 `run_pipeline` `NotImplementedError` stub with this exact function:

```python
def run_pipeline(raws: list[RawDeal], geocoder, conn, now) -> int:
    """Chain every raw through normalize -> classify -> geocode_deal with per-row
    try/except (one bad row never aborts the batch), then dedup the survivors and
    upsert them. Returns the number of rows upserted. FULLY IMPLEMENTED (not a stub).
    """
    deals: list[Deal] = []
    for raw in raws:
        try:
            normalized = normalize(raw)
            deal = classify(normalized)
            deal = geocode_deal(deal, geocoder)
            deals.append(deal)
        except Exception:
            # One malformed raw must not abort the batch.
            continue
    deals = dedup(deals)
    return upsert_deals(conn, deals, now)
```

- [ ] **Step 4 — Run it, expect PASS.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_pipeline_integration.py -v`
  Expected: PASS, 3 passed.

- [ ] **Step 5 — Commit.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git add scrapers/pipeline.py tests/test_pipeline_integration.py && git commit -m "feat(pipeline): implement run_pipeline end-to-end (TDD)"
```

### Task 2.10: Full-suite green + NotImplementedError guard

**Files:** _(none changed — verification gate)_

- [ ] **Step 1 — Run the full M2 test surface.** Run: `cd /Users/jaehunb/projects/freemap && pytest tests/test_normalize.py tests/test_classify.py tests/test_geocode.py tests/test_dedup.py tests/test_upsert_freshness.py tests/test_pipeline_integration.py -v`
  Expected: PASS — all M2 tests green (4 + 14 + 11 + 6 + 10 + 3 = 48 passed).

- [ ] **Step 2 — Run the entire repo test suite (no regressions).** Run: `cd /Users/jaehunb/projects/freemap && pytest -q`
  Expected: PASS, 0 failed. (M1 skeleton tests, if any, still pass.)

- [ ] **Step 3 — Guard: NO NotImplementedError remains in `scrapers/`.** Run: `cd /Users/jaehunb/projects/freemap && grep -rn "raise NotImplementedError" scrapers/ ; echo "exit=$?"`
  Expected: NO matching lines printed and `exit=1` (grep exit code 1 = "no matches found"). If ANY line prints, that function is still a stub — go back and implement it before proceeding.

- [ ] **Step 4 — Sanity-import every scrapers module to confirm nothing broke.** Run: `cd /Users/jaehunb/projects/freemap && python -c "import scrapers.pipeline, scrapers.db, scrapers.geocode, scrapers.contract, scrapers.config; print('import ok')"`
  Expected: prints `import ok`.

- [ ] **Step 5 — Commit the milestone close-out.** Run:
```bash
cd /Users/jaehunb/projects/freemap && git commit --allow-empty -m "chore(m2): pipeline stages + run_pipeline + fetch_all_deals green, no NotImplementedError remains"
```

**End state:** normalize, classify, geocode_deal, dedup, compute_status, the real cache-first `Geocoder`, `upsert_deals`, `fetch_all_deals`, and `run_pipeline` are all implemented test-first and green; both M1 stubs are replaced; `grep -rn "raise NotImplementedError" scrapers/` returns nothing.

---

The repo is greenfield — only the spec exists. My milestone assumes Milestones 1 and 2 have created the package skeleton (contract, config, db, geocode, pipeline) per the canonical interfaces. I have everything I need. Here is Milestone 3.

## Milestone 3: Reddit source + orchestration

**Goal:** Stand up the first real scraper (`scrapers/sources/reddit.py`) against a recorded fixture, then wire `scrapers/run.py` with the canonical `SOURCES` registry and `run_all`, proving end-to-end real rows in a temp DB with failure-isolated orchestration.

---

### Task 3.1: Record the Reddit fixture payload

**Files:** `tests/fixtures/reddit_sample.json`

This is a realistic slice of the Reddit listing JSON shape (`data.children[].data`). It contains three posts: (1) a free in-store Seattle deal with location text, (2) an online freebie, (3) a BOGO online deal. The Reddit JSON listing endpoint returns posts under `data.children`, each child being `{"kind": "t3", "data": {...post fields...}}`. Timestamps are POSIX seconds in `created_utc`.

- [ ] Create the directory: `mkdir -p tests/fixtures`
- [ ] Write `tests/fixtures/reddit_sample.json` with exactly this content:

```json
{
  "kind": "Listing",
  "data": {
    "after": null,
    "before": null,
    "children": [
      {
        "kind": "t3",
        "data": {
          "id": "abc123",
          "title": "Free coffee at Victrola Coffee on Capitol Hill today only",
          "permalink": "/r/Seattle/comments/abc123/free_coffee/",
          "url": "https://www.reddit.com/r/Seattle/comments/abc123/free_coffee/",
          "selftext": "Victrola Coffee Roasters is giving away free drip coffee all day. Capitol Hill, Seattle.",
          "created_utc": 1718668800,
          "subreddit": "Seattle"
        }
      },
      {
        "kind": "t3",
        "data": {
          "id": "def456",
          "title": "Free ebook download from O'Reilly this week",
          "permalink": "/r/Seattle/comments/def456/free_ebook/",
          "url": "https://www.example.com/free-ebook",
          "selftext": "Grab a free programming ebook online, no strings attached.",
          "created_utc": 1718582400,
          "subreddit": "Seattle"
        }
      },
      {
        "kind": "t3",
        "data": {
          "id": "ghi789",
          "title": "Buy one get one free movie tickets online",
          "permalink": "/r/Seattle/comments/ghi789/bogo_movie/",
          "url": "https://www.example.com/bogo-tickets",
          "selftext": "BOGO movie tickets through the app, redeem online.",
          "created_utc": 1718496000,
          "subreddit": "Seattle"
        }
      }
    ]
  }
}
```

- [ ] Verify the JSON is valid: `python -c "import json; d=json.load(open('tests/fixtures/reddit_sample.json')); print(len(d['data']['children']), 'posts')"`
  Expected output: `3 posts`
- [ ] Commit:
```bash
git add tests/fixtures/reddit_sample.json
git commit -m "test(fixtures): add recorded Reddit listing sample payload"
```

---

### Task 3.2: Write the failing contract test for `reddit.fetch`

**Files:** `tests/test_reddit_source.py`

We test `reddit.fetch(config)` ONLY against the recorded fixture by monkeypatching `httpx.get` — never live network. The test asserts the returned list contains valid `RawDeal` objects with the correct `source`, `source_id`, location text, and parsed `posted_at`.

- [ ] Write `tests/test_reddit_source.py` with exactly this content:

```python
import json
from datetime import datetime
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import reddit

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_sample.json"


class FakeResponse:
    """Minimal stand-in for httpx.Response: only what reddit.fetch uses."""

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def make_config() -> Config:
    return Config(
        metro="seattle",
        db_path="db/deals.db",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["reddit"],
        sources={"reddit": {"listing_urls": ["https://www.reddit.com/r/Seattle/.json"]}},
    )


def test_fetch_returns_rawdeals(monkeypatch):
    payload = json.loads(FIXTURE.read_text())

    captured = {}

    def fake_get(url, *args, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return FakeResponse(payload)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = reddit.fetch(make_config())

    assert isinstance(deals, list)
    assert len(deals) == 3
    assert all(isinstance(d, RawDeal) for d in deals)

    # User-Agent from config must be forwarded on the outbound request.
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"
    # The configured listing URL must have been used.
    assert captured["url"] == "https://www.reddit.com/r/Seattle/.json"


def test_fetch_maps_fields(monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse(payload))

    deals = reddit.fetch(make_config())
    by_id = {d.source_id: d for d in deals}

    coffee = by_id["abc123"]
    assert coffee.source == "reddit"
    assert coffee.title == "Free coffee at Victrola Coffee on Capitol Hill today only"
    assert coffee.url == "https://www.reddit.com/r/Seattle/comments/abc123/free_coffee/"
    assert coffee.raw_location is not None  # in-store deal carries location text
    assert isinstance(coffee.posted_at, datetime)
    assert coffee.posted_at == datetime.fromtimestamp(1718668800)
    assert coffee.raw["subreddit"] == "Seattle"


def test_fetch_never_raises_on_bad_listing(monkeypatch):
    # A malformed listing (no children) must yield [] rather than crashing,
    # so one bad subreddit response never aborts the source.
    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse({"data": {}}))
    deals = reddit.fetch(make_config())
    assert deals == []
```

- [ ] Run it, expecting failure because `scrapers/sources/reddit.py` does not yet implement `fetch`:
  `pytest tests/test_reddit_source.py -v`
  Expected: FAIL with `AttributeError: module 'scrapers.sources.reddit' has no attribute 'fetch'` (or `ImportError`).
- [ ] Commit the failing test:
```bash
git add tests/test_reddit_source.py
git commit -m "test(reddit): add failing contract test for reddit.fetch against fixture"
```

---

### Task 3.3: Implement `reddit.fetch` to make the test pass

**Files:** `scrapers/sources/reddit.py`

`fetch(config)` reads `config.user_agent` and `config.sources["reddit"]`, requests each configured listing URL via `httpx.get` (monkeypatched in tests), parses the `data.children[].data` shape, and maps each post to a `RawDeal`. `raw_location` is derived heuristically: physical deals are detected by Seattle neighborhood/venue keywords in the title or selftext; everything else stays `None` (the pipeline's `classify` then routes it online). The function never raises — a malformed listing yields `[]`.

- [ ] Write `scrapers/sources/reddit.py` with exactly this content:

```python
"""Reddit source: fetch free/BOGO deal posts from configured listing URLs.

Reads config.user_agent and config.sources["reddit"]. Tested only against
recorded payloads by monkeypatching httpx.get; never hits the live network here.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal

# Lower-cased substrings that signal a physical Seattle location in free text.
# Used to populate raw_location; classify() turns a non-None location into
# placement="physical". Conservative on purpose — false negatives just demote
# a deal to the list view, never drop it.
_LOCATION_KEYWORDS = (
    "capitol hill",
    "ballard",
    "fremont",
    "downtown",
    "u district",
    "university district",
    "queen anne",
    "west seattle",
    "south lake union",
    "slu",
    "belltown",
    "seattle",
    "bellevue",
    "ave",
    "avenue",
    "street",
    "st.",
    "blvd",
)


def _extract_location(title: str, selftext: str | None) -> str | None:
    """Return a location string if the text mentions a known physical place."""
    haystack = f"{title} {selftext or ''}".lower()
    for kw in _LOCATION_KEYWORDS:
        if kw in haystack:
            # Hand the original (cased) text to the geocoder; it is the most
            # informative thing we have for a free-text Reddit post.
            return selftext or title
    return None


def _post_to_rawdeal(post: dict) -> RawDeal | None:
    """Map one Reddit post 'data' dict to a RawDeal. Returns None if unusable."""
    source_id = post.get("id")
    title = post.get("title")
    if not source_id or not title:
        return None

    permalink = post.get("permalink")
    url = post.get("url") or (
        f"https://www.reddit.com{permalink}" if permalink else ""
    )

    selftext = post.get("selftext") or None

    posted_at = None
    created = post.get("created_utc")
    if isinstance(created, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(created)
        except (OverflowError, OSError, ValueError):
            posted_at = None

    return RawDeal(
        source="reddit",
        source_id=source_id,
        title=title,
        url=url,
        description=selftext,
        raw_location=_extract_location(title, selftext),
        posted_at=posted_at,
        expires_at=None,
        raw=post,
    )


def fetch(config: Config) -> list[RawDeal]:
    """Fetch RawDeals from every configured Reddit listing URL.

    Never raises: a failed request or malformed listing for one URL is skipped
    so a single bad listing cannot abort the whole source.
    """
    settings = config.sources.get("reddit", {})
    listing_urls = settings.get("listing_urls", [])
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in listing_urls:
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            # One bad listing URL is skipped, not fatal.
            continue

        children = (payload or {}).get("data", {}).get("children", [])
        for child in children:
            post = (child or {}).get("data", {})
            raw_deal = _post_to_rawdeal(post)
            if raw_deal is not None:
                deals.append(raw_deal)

    return deals
```

- [ ] Run the contract test, expecting it to pass:
  `pytest tests/test_reddit_source.py -v`
  Expected: PASS, 3 passed.
- [ ] Run the full suite to confirm nothing regressed:
  `pytest -q`
  Expected: PASS (all prior tests still green).
- [ ] Commit:
```bash
git add scrapers/sources/reddit.py
git commit -m "feat(reddit): implement fetch parsing Reddit listing JSON into RawDeals"
```

---

### Task 3.4: Write the failing test for the `run.py` happy path

**Files:** `tests/test_run_reddit_integration.py`

> This is a NEW file, distinct from Milestone 2's `tests/test_pipeline_integration.py` (which covers `run_pipeline` directly). Using a separate filename keeps M2's `run_pipeline` coverage intact rather than overwriting it.

This test exercises `run_all` over a single-source dict `{"reddit": reddit.fetch}` against a real temp SQLite DB with a `FakeGeocoder`, then asserts: the function returns the canonical `{source: {deals_found, upserted, errors}}` shape, rows landed with correct `placement`/`deal_type`, and a `scrape_runs` row was recorded. We seed the geocoder so the physical coffee deal geocodes to a Seattle coordinate.

- [ ] Write `tests/test_run_reddit_integration.py` with exactly this content:

```python
import json
from datetime import datetime
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.db import connect, init_db
from scrapers.geocode import FakeGeocoder
from scrapers.sources import reddit
from scrapers import run

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_sample.json"
NOW = datetime(2026, 6, 18, 12, 0, 0)


def make_config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["reddit"],
        sources={"reddit": {"listing_urls": ["https://www.reddit.com/r/Seattle/.json"]}},
    )


def patch_reddit(monkeypatch):
    payload = json.loads(FIXTURE.read_text())

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(httpx, "get", lambda url, *a, **k: FakeResponse())


def test_run_all_single_source_writes_rows(tmp_path, monkeypatch):
    patch_reddit(monkeypatch)

    db_file = tmp_path / "deals.db"
    conn = connect(str(db_file))
    init_db(conn)

    # Seed the geocoder so the physical coffee deal resolves to a Seattle point.
    selftext = (
        "Victrola Coffee Roasters is giving away free drip coffee all day. "
        "Capitol Hill, Seattle."
    )
    geocoder = FakeGeocoder({selftext: (47.6231, -122.3170)})

    summary = run.run_all(
        make_config(),
        conn,
        geocoder,
        NOW,
        sources={"reddit": reddit.fetch},
    )

    # Canonical return shape.
    assert set(summary.keys()) == {"reddit"}
    assert summary["reddit"]["deals_found"] == 3
    assert summary["reddit"]["upserted"] == 3
    assert summary["reddit"]["errors"] is None

    rows = conn.execute(
        "SELECT source_id, deal_type, placement, geocode_status, lat, lng "
        "FROM deals ORDER BY source_id"
    ).fetchall()
    by_id = {r["source_id"]: r for r in rows}
    assert len(by_id) == 3

    coffee = by_id["abc123"]
    assert coffee["deal_type"] == "free"
    assert coffee["placement"] == "physical"
    assert coffee["geocode_status"] == "ok"
    assert coffee["lat"] == 47.6231
    assert coffee["lng"] == -122.3170

    ebook = by_id["def456"]
    assert ebook["deal_type"] == "free"
    assert ebook["placement"] == "online"

    bogo = by_id["ghi789"]
    assert bogo["deal_type"] == "bogo"
    assert bogo["placement"] == "online"

    # A scrape_runs row was recorded for the source.
    run_rows = conn.execute(
        "SELECT source, deals_found, errors FROM scrape_runs"
    ).fetchall()
    assert len(run_rows) == 1
    assert run_rows[0]["source"] == "reddit"
    assert run_rows[0]["deals_found"] == 3
    assert run_rows[0]["errors"] is None
```

- [ ] Run it, expecting failure because `scrapers/run.py` does not yet define `run_all`:
  `pytest tests/test_run_reddit_integration.py -v`
  Expected: FAIL with `AttributeError: module 'scrapers.run' has no attribute 'run_all'` (or `ImportError`).
- [ ] Commit the failing test:
```bash
git add tests/test_run_reddit_integration.py
git commit -m "test(run): add failing happy-path integration test for run_all over reddit"
```

---

### Task 3.5: Implement `scrapers/run.py` with the `SOURCES` registry and `run_all`

**Files:** `scrapers/run.py`

Implement the canonical module-level `SOURCES` registry (reddit-only for now) and `run_all(config, conn, geocoder, now, sources=None) -> dict[str, dict]` — verbatim to the canonical signatures. `run_all` wraps each source's fetch + `run_pipeline` in try/except, calls `record_run` on both success and failure, and returns `{source: {deals_found, upserted, errors}}`. The `main()` CLI entrypoint is added later in Milestone 6. This task only needs to satisfy the happy-path test (3.4); the failure-isolation test follows in 3.6.

- [ ] Write `scrapers/run.py` with exactly this content:

```python
"""Orchestrate all sources through the pipeline and record scrape_runs.

Single unattended entrypoint (`python -m scrapers.run`) with zero secrets —
suitable for `meshclaw run TASK.md` on cron. One source failing never aborts
the others; every source's outcome is recorded in scrape_runs.
"""
from __future__ import annotations

from datetime import datetime

from scrapers.config import Config
from scrapers.db import record_run
from scrapers.pipeline import run_pipeline
from scrapers.sources import reddit

# Module-level registry: source name -> fetch callable.
# Milestone 3 wires only reddit; Milestone 5 adds chains/slickdeals/local;
# Milestone 6 adds the main() CLI entrypoint (which imports connect/init_db/
# load_config/Geocoder). Keep this registry the single source of truth.
SOURCES: dict[str, callable] = {"reddit": reddit.fetch}


def run_all(
    config: Config,
    conn,
    geocoder,
    now: datetime,
    sources: dict | None = None,
) -> dict[str, dict]:
    """Run each source's fetch -> pipeline, recording every outcome.

    `sources` defaults to the enabled subset of the SOURCES registry; tests
    inject a custom dict. For each source the fetch + run_pipeline are wrapped
    in try/except so one failing source never aborts the others.

    Returns {source_name: {"deals_found": int, "upserted": int,
                           "errors": str | None}}.
    """
    if sources is None:
        sources = {name: SOURCES[name] for name in config.sources_enabled}

    summary: dict[str, dict] = {}
    for name, fetch in sources.items():
        started_at = now
        try:
            raws = fetch(config)
            deals_found = len(raws)
            upserted = run_pipeline(raws, geocoder, conn, now)
            finished_at = datetime.now()
            record_run(conn, name, started_at, finished_at, deals_found, None)
            summary[name] = {
                "deals_found": deals_found,
                "upserted": upserted,
                "errors": None,
            }
        except Exception as e:  # noqa: BLE001 - isolate one source's failure
            finished_at = datetime.now()
            record_run(conn, name, started_at, finished_at, 0, str(e))
            summary[name] = {
                "deals_found": 0,
                "upserted": 0,
                "errors": str(e),
            }
    return summary
```

> The `main()` CLI entrypoint and `if __name__ == "__main__"` block are deliberately NOT added here — Milestone 6 adds them (and the `connect`/`init_db`/`load_config`/`Geocoder` imports they require). Milestone 3 only needs the `SOURCES` registry and `run_all`.

- [ ] Run the happy-path test, expecting it to pass:
  `pytest tests/test_run_reddit_integration.py -v`
  Expected: PASS, 1 passed.
- [ ] Run the full suite to confirm no regressions:
  `pytest -q`
  Expected: PASS (all tests green).
- [ ] Commit:
```bash
git add scrapers/run.py
git commit -m "feat(run): add SOURCES registry and run_all orchestrator"
```

---

### Task 3.6: Write the failing failure-isolation test for `run_all`

**Files:** `tests/test_run_reddit_integration.py`

Add a second test: inject `{"reddit": reddit.fetch, "boom": <fetch that raises>}` and assert that (a) `run_all` does NOT raise, (b) `reddit` still upserts its rows, (c) `boom` is recorded with a non-None error, and (d) `scrape_runs` has a row for each source — proving one source's failure never breaks the run.

- [ ] Append this test to `tests/test_run_reddit_integration.py` (after the existing test; reuses the module-level imports, `make_config`, `patch_reddit`, and `NOW`):

```python
def test_run_all_isolates_failing_source(tmp_path, monkeypatch):
    patch_reddit(monkeypatch)

    db_file = tmp_path / "deals.db"
    conn = connect(str(db_file))
    init_db(conn)

    selftext = (
        "Victrola Coffee Roasters is giving away free drip coffee all day. "
        "Capitol Hill, Seattle."
    )
    geocoder = FakeGeocoder({selftext: (47.6231, -122.3170)})

    def boom(config):
        raise RuntimeError("source exploded")

    # run_all must NOT raise even though one source throws.
    summary = run.run_all(
        make_config(),
        conn,
        geocoder,
        NOW,
        sources={"reddit": reddit.fetch, "boom": boom},
    )

    # reddit still succeeded and upserted its rows.
    assert summary["reddit"]["upserted"] == 3
    assert summary["reddit"]["errors"] is None

    # boom recorded an error and upserted nothing.
    assert summary["boom"]["upserted"] == 0
    assert summary["boom"]["errors"] is not None
    assert "source exploded" in summary["boom"]["errors"]

    # reddit's rows actually landed in the DB despite boom failing.
    deal_count = conn.execute("SELECT COUNT(*) AS n FROM deals").fetchone()["n"]
    assert deal_count == 3

    # scrape_runs has one row per source; boom's carries the error string.
    run_rows = {
        r["source"]: r
        for r in conn.execute(
            "SELECT source, deals_found, errors FROM scrape_runs"
        ).fetchall()
    }
    assert set(run_rows.keys()) == {"reddit", "boom"}
    assert run_rows["reddit"]["errors"] is None
    assert run_rows["reddit"]["deals_found"] == 3
    assert run_rows["boom"]["errors"] is not None
    assert run_rows["boom"]["deals_found"] == 0
```

- [ ] Run just this new test, expecting it to PASS already (the `run_all` from Task 3.5 already isolates failures — this test locks that behavior in):
  `pytest tests/test_run_reddit_integration.py::test_run_all_isolates_failing_source -v`
  Expected: PASS, 1 passed.
- [ ] Confirm the whole integration file is green:
  `pytest tests/test_run_reddit_integration.py -v`
  Expected: PASS, 2 passed.
- [ ] Commit:
```bash
git add tests/test_run_reddit_integration.py
git commit -m "test(run): assert run_all isolates a failing source and records its error"
```

---

### Task 3.7: Add Reddit listing URLs to `config.toml` and verify end-to-end wiring

**Files:** `config.toml`

Ensure the committed `config.toml` carries a real `[sources.reddit]` table with `listing_urls`, so `run_all` with `sources=None` (the production path) resolves `reddit` from the enabled list and `reddit.fetch` finds its URLs. We verify by loading the real config and asserting the flat `Config` shape exposes the Reddit settings.

- [ ] Read the current `config.toml` to see its existing tables: `cat config.toml`
- [ ] Ensure `config.toml` contains a `[sources.reddit]` table. If absent, add this section (leave existing `[meta]`, `[freshness]`, `[geocoder]` tables untouched):

```toml
[sources.reddit]
subreddits = ["Seattle"]
listing_urls = ["https://www.reddit.com/r/Seattle/.json"]
```

- [ ] Verify `load_config` exposes the Reddit settings on the flat `Config`:
```bash
python -c "from scrapers.config import load_config; c = load_config('config.toml'); print('reddit' in c.sources_enabled, c.sources['reddit']['listing_urls'])"
```
  Expected output: `True ['https://www.reddit.com/r/Seattle/.json']`
- [ ] Run the full suite one last time for this milestone:
  `pytest -q`
  Expected: PASS (all tests green).
- [ ] Commit:
```bash
git add config.toml
git commit -m "chore(config): wire reddit listing_urls so run_all resolves the live source"
```

**End state:** `reddit.fetch` parses recorded Reddit JSON into valid `RawDeal`s; `scrapers/run.py` exposes the canonical `SOURCES` registry (reddit-only) and a fully-isolated `run_all` (the `main` CLI entrypoint is added in Milestone 6); real rows land in a temp DB with correct `placement`/`deal_type`/`geocode_status`; a `scrape_runs` row is recorded per source; and one source failing provably never aborts the others. The pipeline is now proven against a real source.

---

I have read the full spec. Now I'll output the complete Milestone 4 markdown, using the canonical interfaces verbatim.

## Milestone 4: API + frontend

Goal: Stand up the read-only FastAPI layer (overridable `get_conn`/`get_now`/`get_stale_after_hours`, filtered+collapsed `/api/deals`, detail, `/api/meta`, StaticFiles for `web/`) with deterministic TestClient tests, then build the Leaflet+list frontend on top of unit-tested pure JS helpers — yielding the first visible product over real data.

### Task 4.1: Add a reusable seeded-DB test fixture

**Files:** `tests/conftest.py`

- [ ] Read the current `tests/conftest.py` (it exists from earlier milestones; you will APPEND a fixture, not rewrite existing ones). Run: `cat tests/conftest.py` to confirm what is already defined (e.g. `FakeGeocoder` helpers, `temp_db`). Do not remove anything.

- [ ] Append a seeded-DB fixture that builds a temp SQLite file with a known mix of active / stale / expired / online / failed-geocode / deduped rows, all stamped relative to the canonical fixed now. **Reuse** the `NOW` constant already defined in `tests/conftest.py` by Milestone 1 (`datetime(2026, 6, 18, 12, 0, 0)`) rather than introducing a second constant — `FIXED_NOW` is simply an alias of it so the API tests read clearly. Add this to the END of `tests/conftest.py`:

```python
from datetime import timedelta

import pytest

from scrapers.db import connect, init_db

# Alias of the canonical NOW (defined in M1) that the API tests pin get_now() to.
# Same value — do NOT redefine a different datetime; keep one source of truth.
FIXED_NOW = NOW  # NOW = datetime(2026, 6, 18, 12, 0, 0) from Milestone 1


def _insert_deal(conn, **cols):
    """Insert one fully-specified deals row. Caller passes every column we seed."""
    keys = list(cols.keys())
    placeholders = ", ".join(f":{k}" for k in keys)
    columns = ", ".join(keys)
    conn.execute(
        f"INSERT INTO deals ({columns}) VALUES ({placeholders})",
        cols,
    )


@pytest.fixture
def seeded_db(tmp_path):
    """A temp deals.db seeded with deterministic rows for API tests.

    Rows (relative to FIXED_NOW = 2026-06-18 12:00:00):
      id=1  active physical food/free      in-bbox  (Capitol Hill)
      id=2  active physical retail/bogo    OUT-of-bbox (far east lng)
      id=3  stale  physical food/free      in-bbox  last_seen 48h ago
      id=4  expired physical event/other   in-bbox  expires_at 1h ago
      id=5  active online food/free        no lat/lng, geocode_status n/a
      id=6  active physical food/free      in-bbox, FAILED geocode (no lat/lng)
      id=7  active physical food/free      in-bbox, SAME dedup_key as id=1 (alt url)
    """
    db_file = tmp_path / "deals.db"
    conn = connect(str(db_file))
    init_db(conn)

    fresh = (FIXED_NOW - timedelta(hours=1)).isoformat()        # within stale window
    stale_seen = (FIXED_NOW - timedelta(hours=48)).isoformat()  # older than 24h
    expired_at = (FIXED_NOW - timedelta(hours=1)).isoformat()
    future = (FIXED_NOW + timedelta(days=30)).isoformat()
    posted = (FIXED_NOW - timedelta(hours=2)).isoformat()

    # id=1 active physical food/free, in-bbox, dedup_key "k1"
    _insert_deal(
        conn, id=1, source="reddit", source_id="r1", dedup_key="k1",
        title="Free coffee Capitol Hill", url="https://example.com/r1",
        description="free drip", deal_type="free", category="food",
        placement="physical", lat=47.62, lng=-122.32, raw_location="Capitol Hill",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=2 active physical retail/bogo, OUT of bbox (lng far east)
    _insert_deal(
        conn, id=2, source="slickdeals", source_id="s2", dedup_key="k2",
        title="BOGO shoes", url="https://example.com/s2",
        description="buy one get one", deal_type="bogo", category="retail",
        placement="physical", lat=47.60, lng=-121.00, raw_location="Bellevue",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=3 stale physical food/free, in-bbox, last_seen 48h ago
    _insert_deal(
        conn, id=3, source="reddit", source_id="r3", dedup_key="k3",
        title="Free pizza slice", url="https://example.com/r3",
        description="free pizza", deal_type="free", category="food",
        placement="physical", lat=47.61, lng=-122.33, raw_location="Ballard",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=stale_seen, status="active",
    )
    # id=4 expired physical event/other, in-bbox, expires_at 1h ago
    _insert_deal(
        conn, id=4, source="local", source_id="l4", dedup_key="k4",
        title="Free festival entry", url="https://example.com/l4",
        description="festival", deal_type="other", category="event",
        placement="physical", lat=47.63, lng=-122.34, raw_location="Fremont",
        geocode_status="ok", posted_at=posted, expires_at=expired_at,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=5 active online food/free, no coords
    _insert_deal(
        conn, id=5, source="slickdeals", source_id="s5", dedup_key="k5",
        title="Free meal kit code", url="https://example.com/s5",
        description="online code", deal_type="free", category="food",
        placement="online", lat=None, lng=None, raw_location=None,
        geocode_status="n/a", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=6 active physical food/free, FAILED geocode, in-bbox conceptually but no coords
    _insert_deal(
        conn, id=6, source="reddit", source_id="r6", dedup_key="k6",
        title="Free burrito somewhere", url="https://example.com/r6",
        description="free burrito", deal_type="free", category="food",
        placement="physical", lat=None, lng=None, raw_location="near the thing",
        geocode_status="failed", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    # id=7 active physical food/free, in-bbox, SAME dedup_key as id=1 -> collapses
    _insert_deal(
        conn, id=7, source="slickdeals", source_id="s7", dedup_key="k1",
        title="Free coffee Capitol Hill", url="https://example.com/s7",
        description="free drip alt", deal_type="free", category="food",
        placement="physical", lat=47.62, lng=-122.32, raw_location="Capitol Hill",
        geocode_status="ok", posted_at=posted, expires_at=future,
        first_seen=posted, last_seen=fresh, status="active",
    )
    conn.commit()
    yield conn, str(db_file)
    conn.close()
```

- [ ] Sanity-check the fixture imports and the DB seeds without error. Run: `pytest tests/conftest.py -q` Expected: `no tests ran` (conftest holds no tests) with NO import/collection errors. If you see a collection error, fix the import/seed before continuing.

- [ ] Commit. Run:

```bash
git add tests/conftest.py && git commit -m "test(api): add deterministic seeded_db fixture with FIXED_NOW"
```

### Task 4.2: Failing test — `GET /api/deals` returns active in-bbox deals and excludes expired

**Files:** `tests/test_api.py`

- [ ] Create `tests/test_api.py` with the TestClient harness that overrides BOTH `get_conn` AND `get_now`, plus the first behavioral test. Write the file:

```python
import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_conn, get_now
from tests.conftest import FIXED_NOW


@pytest.fixture
def client(seeded_db):
    """TestClient with get_conn + get_now pinned to the seeded DB and FIXED_NOW."""
    conn, _db_path = seeded_db

    def _override_conn():
        # Reuse the already-open seeded connection; do NOT close per-request.
        return conn

    def _override_now():
        return FIXED_NOW

    app.dependency_overrides[get_conn] = _override_conn
    app.dependency_overrides[get_now] = _override_now
    yield TestClient(app)
    app.dependency_overrides.clear()


# Seattle-ish bbox = minLng,minLat,maxLng,maxLat. Excludes Bellevue (lng -121.00).
BBOX = "-122.45,47.50,-122.20,47.75"


def test_deals_active_in_bbox_excludes_expired_and_out_of_bbox(client):
    resp = client.get(f"/api/deals?bbox={BBOX}")
    assert resp.status_code == 200
    ids = {d["id"] for d in resp.json()}
    # id=1/id=7 collapse to one (dedup_key k1); id=3 is stale (excluded by default);
    # id=4 expired (always excluded); id=2 out of bbox; id=5 online/id=6 failed have
    # no coords so they are not returned by a bbox map query.
    assert 4 not in ids          # expired always excluded
    assert 2 not in ids          # out of bbox
    assert 3 not in ids          # stale excluded by default
    # id=1 present (collapsed primary), id=7 collapsed into it
    assert 1 in ids
    assert 7 not in ids
```

- [ ] Run it, expecting an IMPORT failure because `api/main.py` does not yet exist (or has no `app`/deps). Run: `pytest tests/test_api.py -q` Expected: FAIL with `ModuleNotFoundError: No module named 'api.main'` or `ImportError: cannot import name 'app'`.

- [ ] Commit the failing test. Run:

```bash
git add tests/test_api.py && git commit -m "test(api): failing test for /api/deals bbox + expired exclusion"
```

### Task 4.3: Implement `api/main.py` minimally to pass Task 4.2

**Files:** `api/__init__.py`, `api/main.py`

- [ ] Ensure the package marker exists. Run: `test -f api/__init__.py || touch api/__init__.py` (no output on success).

- [ ] Create `api/main.py` with the canonical overridable dependencies and a `/api/deals` that filters bbox, excludes expired, excludes stale (default), and collapses `dedup_key` into one record with `alt_urls[]`. Write the file:

```python
"""FreeMap read-only API. All business logic lives in the pipeline; this layer
only queries SQLite and shapes JSON."""

import sqlite3
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException

from scrapers.config import load_config
from scrapers.db import connect, fetch_all_deals
from scrapers.pipeline import compute_status

app = FastAPI(title="FreeMap Seattle API")

_CONFIG = load_config()


# --- Overridable dependencies (tests pin time + DB) -------------------------

def get_conn() -> sqlite3.Connection:
    """FastAPI dependency. Tests override via app.dependency_overrides."""
    return connect(_CONFIG.db_path)


def get_now() -> datetime:
    """Current wall-clock time. Tests MUST override to a fixed NOW."""
    return datetime.now()


def get_stale_after_hours() -> int:
    return load_config().stale_after_hours


# --- Helpers ----------------------------------------------------------------

def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _row_to_deal(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "source": row["source"],
        "source_id": row["source_id"],
        "dedup_key": row["dedup_key"],
        "title": row["title"],
        "url": row["url"],
        "description": row["description"],
        "deal_type": row["deal_type"],
        "category": row["category"],
        "placement": row["placement"],
        "lat": row["lat"],
        "lng": row["lng"],
        "raw_location": row["raw_location"],
        "geocode_status": row["geocode_status"],
        "posted_at": row["posted_at"],
        "expires_at": row["expires_at"],
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "alt_urls": [],
    }


def _in_bbox(deal: dict, bbox) -> bool:
    """bbox = (min_lng, min_lat, max_lng, max_lat). Deals without coords fail bbox."""
    if bbox is None:
        return True
    if deal["lat"] is None or deal["lng"] is None:
        return False
    min_lng, min_lat, max_lng, max_lat = bbox
    return (min_lng <= deal["lng"] <= max_lng) and (min_lat <= deal["lat"] <= max_lat)


def _parse_bbox(bbox: str | None):
    if not bbox:
        return None
    try:
        parts = [float(p) for p in bbox.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be 4 floats")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat")
    return tuple(parts)


def _collapse_dedup(deals: list[dict]) -> list[dict]:
    """Collapse rows sharing a dedup_key into one primary with alt_urls[].
    First-seen wins as primary; others contribute their url to alt_urls.
    Rows with no dedup_key stand alone."""
    primary_by_key: dict = {}
    result: list[dict] = []
    for d in deals:
        key = d["dedup_key"]
        if not key:
            result.append(d)
            continue
        if key not in primary_by_key:
            primary_by_key[key] = d
            result.append(d)
        else:
            prim = primary_by_key[key]
            if d["url"] not in prim["alt_urls"] and d["url"] != prim["url"]:
                prim["alt_urls"].append(d["url"])
    return result


# --- Endpoints --------------------------------------------------------------

@app.get("/api/deals")
def list_deals(
    type: str | None = None,
    category: str | None = None,
    placement: str | None = None,
    bbox: str | None = None,
    include_stale: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
    now: datetime = Depends(get_now),
    stale_after_hours: int = Depends(get_stale_after_hours),
):
    bbox_tuple = _parse_bbox(bbox)
    rows = fetch_all_deals(conn)
    out: list[dict] = []
    for row in rows:
        status = compute_status(
            _parse_dt(row["expires_at"]),
            _parse_dt(row["last_seen"]),
            now,
            stale_after_hours,
        )
        if status == "expired":
            continue
        if status == "stale" and not include_stale:
            continue
        deal = _row_to_deal(row)
        deal["status"] = status
        if type is not None and deal["deal_type"] != type:
            continue
        if category is not None and deal["category"] != category:
            continue
        if placement is not None and deal["placement"] != placement:
            continue
        if not _in_bbox(deal, bbox_tuple):
            continue
        out.append(deal)
    return _collapse_dedup(out)
```

- [ ] Run the Task 4.2 test. Run: `pytest tests/test_api.py -q` Expected: PASS, `1 passed`.

- [ ] Commit. Run:

```bash
git add api/__init__.py api/main.py && git commit -m "feat(api): /api/deals with bbox filter, expired/stale exclusion, dedup collapse"
```

### Task 4.4: Failing tests — stale inclusion, dedup `alt_urls`, type filter

**Files:** `tests/test_api.py`

- [ ] Append three more tests to `tests/test_api.py`:

```python
def test_deals_include_stale_returns_stale_rows(client):
    # Without include_stale, id=3 (stale) is absent.
    base = client.get(f"/api/deals?bbox={BBOX}")
    assert 3 not in {d["id"] for d in base.json()}
    # With include_stale=true, id=3 appears and is marked stale.
    resp = client.get(f"/api/deals?bbox={BBOX}&include_stale=true")
    assert resp.status_code == 200
    by_id = {d["id"]: d for d in resp.json()}
    assert 3 in by_id
    assert by_id[3]["status"] == "stale"
    # Expired (id=4) is STILL excluded even with include_stale.
    assert 4 not in by_id


def test_deals_dedup_collapse_exposes_alt_urls(client):
    resp = client.get(f"/api/deals?bbox={BBOX}")
    by_id = {d["id"]: d for d in resp.json()}
    assert 1 in by_id
    assert 7 not in by_id  # collapsed into id=1
    assert "https://example.com/s7" in by_id[1]["alt_urls"]


def test_deals_type_filter(client):
    # placement=physical + no bbox so we see all non-expired, non-stale physical deals.
    resp = client.get("/api/deals?type=bogo&placement=physical")
    assert resp.status_code == 200
    deals = resp.json()
    assert {d["id"] for d in deals} == {2}  # only the bogo deal (id=2, in or out of bbox irrelevant w/o bbox)
    assert all(d["deal_type"] == "bogo" for d in deals)
```

- [ ] Run the suite, expecting the THREE new tests to PASS already (the implementation in 4.3 covers stale/dedup/type). Run: `pytest tests/test_api.py -q` Expected: PASS, `4 passed`. If `test_deals_type_filter` fails, confirm `_in_bbox` returns `True` when bbox is `None` (it does) — debug only if red.

- [ ] Commit. Run:

```bash
git add tests/test_api.py && git commit -m "test(api): cover stale inclusion, alt_urls collapse, type filter"
```

### Task 4.5: Failing test + implementation — `GET /api/deals/{id}`

**Files:** `tests/test_api.py`, `api/main.py`

- [ ] Append the detail-endpoint test to `tests/test_api.py`:

```python
def test_deal_detail_returns_full_record(client):
    resp = client.get("/api/deals/5")
    assert resp.status_code == 200
    deal = resp.json()
    assert deal["id"] == 5
    assert deal["placement"] == "online"
    assert deal["deal_type"] == "free"


def test_deal_detail_404_for_missing(client):
    resp = client.get("/api/deals/9999")
    assert resp.status_code == 404
```

- [ ] Run it, expecting the new detail tests to FAIL (route not defined yet → 404 for id=5 too, and the missing-id assert may pass coincidentally). Run: `pytest tests/test_api.py -k detail -q` Expected: FAIL on `test_deal_detail_returns_full_record` with `assert 404 == 200` (or similar).

- [ ] Add the detail route to `api/main.py`, immediately AFTER the `list_deals` function:

```python
@app.get("/api/deals/{deal_id}")
def deal_detail(
    deal_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
):
    row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="deal not found")
    return _row_to_deal(row)
```

- [ ] Run the detail tests. Run: `pytest tests/test_api.py -k detail -q` Expected: PASS, `2 passed`.

- [ ] Commit. Run:

```bash
git add tests/test_api.py api/main.py && git commit -m "feat(api): GET /api/deals/{id} detail endpoint with 404"
```

### Task 4.6: Failing test + implementation — `GET /api/meta`

**Files:** `tests/test_api.py`, `api/main.py`

- [ ] Append the meta test to `tests/test_api.py`:

```python
def test_meta_shape_counts_and_last_scrape(client):
    conn, _ = client.app.dependency_overrides  # noqa: not used; keep client active
    # Seed a couple of scrape_runs so meta has data to report.
    real_conn = app.dependency_overrides[get_conn]()
    real_conn.execute(
        "INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors) "
        "VALUES (?, ?, ?, ?, ?)",
        ("reddit", "2026-06-18T06:00:00", "2026-06-18T06:01:00", 4, None),
    )
    real_conn.execute(
        "INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors) "
        "VALUES (?, ?, ?, ?, ?)",
        ("reddit", "2026-06-18T11:00:00", "2026-06-18T11:01:00", 5, None),
    )
    real_conn.execute(
        "INSERT INTO scrape_runs (source, started_at, finished_at, deals_found, errors) "
        "VALUES (?, ?, ?, ?, ?)",
        ("slickdeals", "2026-06-18T11:00:00", None, 0, "boom"),
    )
    real_conn.commit()

    resp = client.get("/api/meta")
    assert resp.status_code == 200
    meta = resp.json()
    assert "sources" in meta
    by_source = {s["source"]: s for s in meta["sources"]}
    # reddit: total deals currently in deals table + last SUCCESSFUL scrape time
    assert by_source["reddit"]["last_successful_scrape"] == "2026-06-18T11:01:00"
    # slickdeals errored -> last_successful_scrape is None
    assert by_source["slickdeals"]["last_successful_scrape"] is None
    # deal_count per source reflects rows in deals table
    assert by_source["reddit"]["deal_count"] == 3  # ids 1, 3, 6 are reddit
```

- [ ] Run it, expecting FAIL because `/api/meta` is not defined. Run: `pytest tests/test_api.py -k meta -q` Expected: FAIL with `assert 404 == 200`.

- [ ] Add the meta route to `api/main.py`, after `deal_detail`:

```python
@app.get("/api/meta")
def meta(conn: sqlite3.Connection = Depends(get_conn)):
    # Per-source deal counts from the serving table.
    count_rows = conn.execute(
        "SELECT source, COUNT(*) AS n FROM deals GROUP BY source"
    ).fetchall()
    counts = {r["source"]: r["n"] for r in count_rows}

    # Last SUCCESSFUL scrape (errors IS NULL) per source from scrape_runs.
    run_rows = conn.execute(
        "SELECT source, MAX(finished_at) AS last_ok "
        "FROM scrape_runs WHERE errors IS NULL AND finished_at IS NOT NULL "
        "GROUP BY source"
    ).fetchall()
    last_ok = {r["source"]: r["last_ok"] for r in run_rows}

    sources = sorted(set(counts) | set(last_ok))
    return {
        "sources": [
            {
                "source": s,
                "deal_count": counts.get(s, 0),
                "last_successful_scrape": last_ok.get(s),
            }
            for s in sources
        ]
    }
```

- [ ] Run the meta test. Run: `pytest tests/test_api.py -k meta -q` Expected: PASS, `1 passed`.

- [ ] Run the full API suite to confirm nothing regressed. Run: `pytest tests/test_api.py -q` Expected: PASS, `8 passed`.

- [ ] Commit. Run:

```bash
git add tests/test_api.py api/main.py && git commit -m "feat(api): GET /api/meta per-source counts + last successful scrape"
```

### Task 4.7: Mount StaticFiles to serve `web/`

**Files:** `api/main.py`, `web/index.html`, `tests/test_api.py`

- [ ] Create a placeholder `web/index.html` so the StaticFiles mount has a directory to serve (the real UI lands in Task 4.11). Write `web/index.html`:

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>FreeMap Seattle</title></head>
<body><p>FreeMap Seattle — loading…</p></body>
</html>
```

- [ ] Append a static-serving test to `tests/test_api.py`:

```python
def test_static_index_served_at_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "FreeMap Seattle" in resp.text
```

- [ ] Run it, expecting FAIL (no mount yet → 404). Run: `pytest tests/test_api.py -k static -q` Expected: FAIL with `assert 404 == 200`.

- [ ] Add the StaticFiles mount at the END of `api/main.py` (it MUST be mounted last so `/api/*` routes are matched first). Add the import near the top with the other FastAPI imports, then the mount at file end:

```python
from fastapi.staticfiles import StaticFiles
```

```python
# Mount LAST so /api/* routes take precedence over the static catch-all.
app.mount("/", StaticFiles(directory="web", html=True), name="web")
```

- [ ] Run the static test. Run: `pytest tests/test_api.py -k static -q` Expected: PASS, `1 passed`.

- [ ] Run the full API suite. Run: `pytest tests/test_api.py -q` Expected: PASS, `9 passed`.

- [ ] Commit. Run:

```bash
git add api/main.py web/index.html tests/test_api.py && git commit -m "feat(api): serve web/ via StaticFiles at /; placeholder index.html"
```

### Task 4.8: `web/filters.js` — `buildQuery(state)` with a Node assertion test

**Files:** `web/filters.js`

- [ ] Create `web/filters.js` exposing the pure `buildQuery(state)`. It builds a `/api/deals` querystring from the filter state. Write the file:

```javascript
// Pure, dependency-free filter helpers. Exposed on window for the browser AND
// exported via module.exports for Node-run unit tests (no build step either way).

// buildQuery(state) -> querystring (no leading "?") for GET /api/deals.
// state shape: { type, category, placement, bbox, includeStale }
// Only truthy filter fields are emitted. bbox is "minLng,minLat,maxLng,maxLat".
function buildQuery(state) {
  state = state || {};
  const params = [];
  if (state.type) params.push("type=" + encodeURIComponent(state.type));
  if (state.category) params.push("category=" + encodeURIComponent(state.category));
  if (state.placement) params.push("placement=" + encodeURIComponent(state.placement));
  if (state.bbox) params.push("bbox=" + encodeURIComponent(state.bbox));
  if (state.includeStale) params.push("include_stale=true");
  return params.join("&");
}

// matchesFilters added in the next task.

if (typeof module !== "undefined" && module.exports) {
  module.exports = { buildQuery };
}
if (typeof window !== "undefined") {
  window.buildQuery = buildQuery;
}
```

- [ ] Run a Node assertion test exercising `buildQuery`. Run:

```bash
node -e '
const { buildQuery } = require("./web/filters.js");
const assert = require("assert");
assert.strictEqual(buildQuery({}), "");
assert.strictEqual(buildQuery({ type: "free" }), "type=free");
assert.strictEqual(
  buildQuery({ type: "bogo", category: "food", includeStale: true }),
  "type=bogo&category=food&include_stale=true"
);
assert.strictEqual(
  buildQuery({ bbox: "-122.45,47.50,-122.20,47.75" }),
  "bbox=-122.45%2C47.50%2C-122.20%2C47.75"
);
console.log("buildQuery OK");
'
```

Expected: prints `buildQuery OK` and exits 0. If it throws an `AssertionError`, fix `buildQuery` before continuing.

- [ ] Commit. Run:

```bash
git add web/filters.js && git commit -m "feat(web): filters.js buildQuery() with node assertion test"
```

### Task 4.9: `web/filters.js` — `matchesFilters(deal, state)` with a Node assertion test

**Files:** `web/filters.js`

- [ ] Add the pure `matchesFilters(deal, state)` to `web/filters.js`. Replace the `// matchesFilters added in the next task.` line with:

```javascript
// matchesFilters(deal, state) -> bool. Client-side guard mirroring server filters
// so a deal already in memory can be re-checked without a refetch. includeStale
// gates stale deals; expired deals never match (server already excludes them, but
// we defend here too).
function matchesFilters(deal, state) {
  state = state || {};
  if (deal.status === "expired") return false;
  if (deal.status === "stale" && !state.includeStale) return false;
  if (state.type && deal.deal_type !== state.type) return false;
  if (state.category && deal.category !== state.category) return false;
  if (state.placement && deal.placement !== state.placement) return false;
  return true;
}
```

- [ ] Update BOTH exports to include `matchesFilters`. In `web/filters.js`, change the `module.exports` line and the `window` assignments:

```javascript
if (typeof module !== "undefined" && module.exports) {
  module.exports = { buildQuery, matchesFilters };
}
if (typeof window !== "undefined") {
  window.buildQuery = buildQuery;
  window.matchesFilters = matchesFilters;
}
```

- [ ] Run a Node assertion test exercising `matchesFilters`. Run:

```bash
node -e '
const { matchesFilters } = require("./web/filters.js");
const assert = require("assert");
const active = { status: "active", deal_type: "free", category: "food", placement: "physical" };
assert.strictEqual(matchesFilters(active, {}), true);
assert.strictEqual(matchesFilters(active, { type: "free" }), true);
assert.strictEqual(matchesFilters(active, { type: "bogo" }), false);
assert.strictEqual(matchesFilters(active, { category: "retail" }), false);
const stale = { status: "stale", deal_type: "free", category: "food", placement: "physical" };
assert.strictEqual(matchesFilters(stale, {}), false);
assert.strictEqual(matchesFilters(stale, { includeStale: true }), true);
const expired = { status: "expired", deal_type: "free", category: "food", placement: "physical" };
assert.strictEqual(matchesFilters(expired, { includeStale: true }), false);
console.log("matchesFilters OK");
'
```

Expected: prints `matchesFilters OK` and exits 0.

- [ ] Commit. Run:

```bash
git add web/filters.js && git commit -m "feat(web): filters.js matchesFilters() with node assertion test"
```

### Task 4.10: `web/list.js` — `belongsInList(deal)` with a Node assertion test

**Files:** `web/list.js`

- [ ] Create `web/list.js` exposing the pure `belongsInList(deal)` (the rendering function comes after the helper is proven). Write the file:

```javascript
// list.js — online deals + failed-geocode physical deals render as cards.
// Pure helper first; rendering wired in after the node assertion passes.

// belongsInList(deal) -> bool. A deal belongs in the list view if it is online,
// OR if it is a physical deal we could not geocode (so it is never lost).
function belongsInList(deal) {
  return deal.placement === "online" || deal.geocode_status === "failed";
}

// renderList(deals, state, container) — DOM rendering, browser-only.
function renderList(deals, state, container) {
  const items = deals
    .filter(belongsInList)
    .filter((d) => window.matchesFilters(d, state));
  container.innerHTML = "";
  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "list-empty";
    empty.textContent = "No matching deals.";
    container.appendChild(empty);
    return;
  }
  for (const d of items) {
    const card = document.createElement("article");
    card.className = "deal-card" + (d.status === "stale" ? " stale" : "");
    const h = document.createElement("h3");
    h.textContent = d.title;
    const meta = document.createElement("p");
    meta.className = "deal-meta";
    meta.textContent = `${d.deal_type} · ${d.category} · ${d.status}`;
    const link = document.createElement("a");
    link.href = d.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "View deal";
    card.appendChild(h);
    card.appendChild(meta);
    card.appendChild(link);
    container.appendChild(card);
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { belongsInList };
}
if (typeof window !== "undefined") {
  window.belongsInList = belongsInList;
  window.renderList = renderList;
}
```

- [ ] Run a Node assertion test exercising `belongsInList`. Run:

```bash
node -e '
const { belongsInList } = require("./web/list.js");
const assert = require("assert");
assert.strictEqual(belongsInList({ placement: "online", geocode_status: "n/a" }), true);
assert.strictEqual(belongsInList({ placement: "physical", geocode_status: "failed" }), true);
assert.strictEqual(belongsInList({ placement: "physical", geocode_status: "ok" }), false);
console.log("belongsInList OK");
'
```

Expected: prints `belongsInList OK` and exits 0.

- [ ] Commit. Run:

```bash
git add web/list.js && git commit -m "feat(web): list.js belongsInList() + renderList with node assertion test"
```

### Task 4.11: `web/index.html` — Leaflet + markercluster scaffold, view toggle, filter sidebar, freshness badge

**Files:** `web/index.html`

- [ ] Replace the placeholder `web/index.html` with the full shell that loads Leaflet 1.9.4 + Leaflet.markercluster 1.5.3 from unpkg (no build step) and our scripts. Write the file:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FreeMap Seattle</title>

  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"
  />
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"
  />
  <link rel="stylesheet" href="/style.css" />
</head>
<body>
  <header id="topbar">
    <h1>FreeMap Seattle</h1>
    <nav id="view-toggle">
      <button id="btn-map" class="active" type="button">Map</button>
      <button id="btn-list" type="button">List</button>
    </nav>
    <span id="freshness-badge">deals as of …</span>
  </header>

  <main id="layout">
    <aside id="filters">
      <h2>Filters</h2>
      <label>Deal type
        <select id="filter-type">
          <option value="">All</option>
          <option value="free">Free</option>
          <option value="bogo">BOGO</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label>Category
        <select id="filter-category">
          <option value="">All</option>
          <option value="food">Food</option>
          <option value="retail">Retail</option>
          <option value="event">Event</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label class="checkbox">
        <input id="filter-stale" type="checkbox" /> Show stale
      </label>
    </aside>

    <section id="map-view"><div id="map"></div></section>
    <section id="list-view" hidden><div id="list"></div></section>
  </main>

  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

  <script src="/filters.js"></script>
  <script src="/list.js"></script>
  <script src="/map.js"></script>
</body>
</html>
```

- [ ] Verify the page loads in a real browser with the FastAPI server serving it. Start the server, then open it. Run:

```bash
uvicorn api.main:app --reload --port 8000
```

Then in a browser open `http://localhost:8000/`. Expected manual observation: the topbar shows "FreeMap Seattle", a Map/List toggle, and a "deals as of …" badge; the Leaflet map container and filter sidebar render with no console 404s for `/filters.js`, `/list.js`, or the unpkg assets. (`/map.js` will 404 until Task 4.12 — that is expected; note it and proceed.) Stop the server with Ctrl-C.

- [ ] Commit. Run:

```bash
git add web/index.html && git commit -m "feat(web): index.html shell — Leaflet+markercluster, view toggle, filters, badge"
```

### Task 4.12: `web/map.js` — bbox fetch on `moveend`, clustered colored pins, stale greying, popups, view toggle, freshness badge

**Files:** `web/map.js`

- [ ] Create `web/map.js` wiring the map, the bbox-driven fetch, colored clustered pins by `deal_type`, greyed stale markers (only when the show-stale toggle is on), popups with details + link, the Map/List view toggle, and the `/api/meta` freshness badge. Write the file:

```javascript
// map.js — orchestrates the FreeMap UI: Leaflet map, bbox fetch on moveend,
// clustered colored pins, list view, filters, and the freshness badge.

const PIN_COLORS = { free: "#1a9850", bogo: "#3b82f6", other: "#9ca3af" };
const SEATTLE = [47.6062, -122.3321];

const filterState = { type: "", category: "", placement: "", bbox: "", includeStale: false };

let map;
let clusterLayer;
let lastDeals = [];

function readFilterState() {
  filterState.type = document.getElementById("filter-type").value;
  filterState.category = document.getElementById("filter-category").value;
  filterState.includeStale = document.getElementById("filter-stale").checked;
}

function currentBbox() {
  const b = map.getBounds();
  // minLng,minLat,maxLng,maxLat
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
}

function markerFor(deal) {
  const color = PIN_COLORS[deal.deal_type] || PIN_COLORS.other;
  const stale = deal.status === "stale";
  const icon = L.divIcon({
    className: "deal-pin" + (stale ? " stale" : ""),
    html: `<span class="pin-dot" style="background:${color};opacity:${stale ? 0.4 : 1}"></span>`,
    iconSize: [16, 16],
  });
  const marker = L.marker([deal.lat, deal.lng], { icon });
  const altLinks = (deal.alt_urls || [])
    .map((u, i) => `<a href="${u}" target="_blank" rel="noopener">alt ${i + 1}</a>`)
    .join(" · ");
  marker.bindPopup(
    `<strong>${deal.title}</strong><br>` +
      `${deal.deal_type} · ${deal.category} · ${deal.status}<br>` +
      `<a href="${deal.url}" target="_blank" rel="noopener">View deal</a>` +
      (altLinks ? `<br>${altLinks}` : "")
  );
  return marker;
}

async function fetchDeals() {
  readFilterState();
  filterState.bbox = currentBbox();
  const qs = window.buildQuery(filterState);
  const resp = await fetch("/api/deals?" + qs);
  lastDeals = await resp.json();
  renderMap();
  renderListView();
}

function renderMap() {
  clusterLayer.clearLayers();
  for (const deal of lastDeals) {
    if (deal.placement !== "physical") continue;
    if (deal.lat == null || deal.lng == null) continue;
    if (!window.matchesFilters(deal, filterState)) continue;
    clusterLayer.addLayer(markerFor(deal));
  }
}

function renderListView() {
  const container = document.getElementById("list");
  window.renderList(lastDeals, filterState, container);
}

async function loadFreshness() {
  try {
    const resp = await fetch("/api/meta");
    const meta = await resp.json();
    const times = (meta.sources || [])
      .map((s) => s.last_successful_scrape)
      .filter(Boolean)
      .sort();
    const latest = times.length ? times[times.length - 1] : null;
    document.getElementById("freshness-badge").textContent = latest
      ? "deals as of " + latest.replace("T", " ")
      : "deals as of —";
  } catch (e) {
    document.getElementById("freshness-badge").textContent = "deals as of —";
  }
}

function showView(which) {
  const mapView = document.getElementById("map-view");
  const listView = document.getElementById("list-view");
  const btnMap = document.getElementById("btn-map");
  const btnList = document.getElementById("btn-list");
  const isMap = which === "map";
  mapView.hidden = !isMap;
  listView.hidden = isMap;
  btnMap.classList.toggle("active", isMap);
  btnList.classList.toggle("active", !isMap);
  if (isMap) map.invalidateSize();
}

function init() {
  map = L.map("map").setView(SEATTLE, 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  clusterLayer = L.markerClusterGroup();
  map.addLayer(clusterLayer);

  map.on("moveend", fetchDeals);

  document.getElementById("filter-type").addEventListener("change", fetchDeals);
  document.getElementById("filter-category").addEventListener("change", fetchDeals);
  document.getElementById("filter-stale").addEventListener("change", fetchDeals);
  document.getElementById("btn-map").addEventListener("click", () => showView("map"));
  document.getElementById("btn-list").addEventListener("click", () => showView("list"));

  loadFreshness();
  fetchDeals(); // initial load (moveend may not fire on first render)
}

document.addEventListener("DOMContentLoaded", init);
```

- [ ] Seed a few rows **offline** (no live network, per the spec's recorded-payload posture) so the map has data, then verify in the browser. Build `db/deals.db` from the recorded Reddit fixture using a short one-off script that monkeypatches `httpx.get` and uses a `FakeGeocoder` — the same offline mechanism Milestone 6 tests with. Run:

```bash
cd /Users/jaehunb/projects/freemap && python -c "
import httpx
from pathlib import Path
from datetime import datetime
from scrapers.db import connect, init_db
from scrapers.geocode import FakeGeocoder
from scrapers.pipeline import run_pipeline
from scrapers.sources import reddit
from scrapers.config import load_config

fixture = Path('tests/fixtures/reddit_sample.json').read_text(encoding='utf-8')
class R:
    status_code = 200
    text = fixture
    def raise_for_status(self): pass
    def json(self): import json; return json.loads(fixture)
httpx.get = lambda *a, **k: R()

cfg = load_config('config.toml')
conn = connect('db/deals.db'); init_db(conn)
geo = FakeGeocoder({'Capitol Hill': (47.6253, -122.3222), 'Capitol Hill, Seattle, WA': (47.6253, -122.3222), 'Downtown Seattle': (47.6062, -122.3321)})
n = run_pipeline(reddit.fetch(cfg), geo, conn, datetime.now()); conn.commit()
print('seeded', n, 'deals into db/deals.db (offline, from reddit fixture)')
"
```

Expected: prints `seeded N deals into db/deals.db (offline, from reddit fixture)` with N ≥ 1; `db/deals.db` now has rows — all from the recorded fixture, no live Reddit or Nominatim call. (The seeded_db fixture in `tests/test_api.py` already proves the API independently; this step just gives the browser something to render.)

- [ ] Run the server and observe the map. Run:

```bash
uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000/`. Expected manual observation: clustered colored pins appear for physical deals (green=free, blue=bogo, grey=other); panning/zooming refetches by bbox (watch the Network tab fire `GET /api/deals?...bbox=...` on `moveend`); clicking a pin opens a popup with title · type · category · status and a working "View deal" link; the freshness badge reads "deals as of <timestamp>" from `/api/meta`. Toggle "Show stale" and confirm greyed stale pins appear/disappear. Stop with Ctrl-C.

- [ ] Commit. Run:

```bash
git add web/map.js && git commit -m "feat(web): map.js bbox fetch, clustered colored pins, popups, view toggle, freshness badge"
```

### Task 4.13: `web/style.css` — layout, pins, freshness/stale styling, list cards

**Files:** `web/style.css`

- [ ] Create `web/style.css` giving the shell a usable layout (full-height map, sidebar, topbar), pin dot styling, stale greying, and list card styling. Write the file:

```css
* { box-sizing: border-box; }

html, body { height: 100%; margin: 0; font-family: system-ui, sans-serif; }

#topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  background: #0f172a;
  color: #fff;
}
#topbar h1 { font-size: 1.1rem; margin: 0; flex: 0 0 auto; }
#view-toggle { display: flex; gap: 0.25rem; }
#view-toggle button {
  background: #1e293b;
  color: #cbd5e1;
  border: none;
  padding: 0.35rem 0.75rem;
  border-radius: 4px;
  cursor: pointer;
}
#view-toggle button.active { background: #2563eb; color: #fff; }
#freshness-badge { margin-left: auto; font-size: 0.85rem; color: #94a3b8; }

#layout {
  display: flex;
  height: calc(100% - 48px);
}
#filters {
  flex: 0 0 220px;
  padding: 1rem;
  border-right: 1px solid #e2e8f0;
  overflow-y: auto;
}
#filters h2 { font-size: 0.95rem; margin-top: 0; }
#filters label { display: block; margin-bottom: 0.75rem; font-size: 0.85rem; }
#filters label.checkbox { display: flex; align-items: center; gap: 0.4rem; }
#filters select { width: 100%; padding: 0.3rem; margin-top: 0.25rem; }

#map-view, #list-view { flex: 1 1 auto; height: 100%; }
#map { height: 100%; width: 100%; }

#list { padding: 1rem; overflow-y: auto; height: 100%; }
.deal-card {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
}
.deal-card.stale { opacity: 0.5; }
.deal-card h3 { margin: 0 0 0.25rem; font-size: 1rem; }
.deal-meta { margin: 0 0 0.5rem; font-size: 0.8rem; color: #64748b; }
.list-empty { color: #94a3b8; }

/* Map pins */
.pin-dot {
  display: block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.3);
}
.deal-pin.stale .pin-dot { box-shadow: none; }
```

- [ ] Verify styling in the browser. Run:

```bash
uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000/`. Expected manual observation: dark topbar with the toggle and right-aligned freshness badge; left filter sidebar; full-height map filling the rest; switching to List shows scrollable deal cards (online + failed-geocode deals) with stale cards visibly dimmed. Stop with Ctrl-C.

- [ ] Commit. Run:

```bash
git add web/style.css && git commit -m "feat(web): style.css layout, pins, stale greying, list cards"
```

### Task 4.14: Milestone verification — full suite + clean end state

**Files:** (no new files)

- [ ] Run the complete Python test suite to confirm the API milestone did not regress earlier milestones. Run: `pytest -q` Expected: PASS, all tests green (API: 9 passed plus all prior milestone tests).

- [ ] Re-run both frontend node assertion tests as a final guard. Run:

```bash
node -e 'const f=require("./web/filters.js");const a=require("assert");a.strictEqual(f.buildQuery({type:"free"}),"type=free");a.strictEqual(f.matchesFilters({status:"active",deal_type:"free"},{type:"free"}),true);console.log("filters OK");' \
&& node -e 'const l=require("./web/list.js");const a=require("assert");a.strictEqual(l.belongsInList({placement:"online"}),true);a.strictEqual(l.belongsInList({placement:"physical",geocode_status:"ok"}),false);console.log("list OK");'
```

Expected: prints `filters OK` then `list OK`.

- [ ] Confirm no `NotImplementedError` stubs were reintroduced and `fetch_all_deals` is real (it must be, from Milestone 2). Run: `grep -rn "NotImplementedError" scrapers/ api/` Expected: no output (exit code 1 from grep, meaning no matches).

- [ ] Final milestone commit (captures any straggler like a `.gitignore` note for `db/deals.db`). Run:

```bash
git add -A && git commit -m "chore(m4): API + frontend milestone complete — visible product over real data" --allow-empty
```

---

The repo currently only has the design doc — M1-M4 haven't been physically built yet (this is a planning exercise; my milestone is drafted to follow the canonical interfaces, which the earlier milestones establish). I have everything I need. Here is Milestone 5.


---

## Milestone 5: Remaining sources

**Goal:** Add `chains`, `slickdeals`, and `local` source modules — each `fetch(config: Config) -> list[RawDeal]` tested against a recorded fixture by monkeypatching `httpx.get` — register all three in the existing `run.py` `SOURCES` registry, and prove `run_all` over all four config-driven sources upserts the survivors even when one source deliberately throws.

> Assumptions inherited from earlier milestones (do NOT re-create these — they already exist and are green):
> - `scrapers/contract.py` defines `RawDeal`/`Deal` verbatim.
> - `scrapers/config.py` defines `Config` + `load_config`; `config.sources` is a dict keyed by source name.
> - `scrapers/pipeline.py` has a fully-implemented `run_pipeline(raws, geocoder, conn, now) -> int` (M2).
> - `scrapers/db.py` has `connect`, `init_db`, `upsert_deals`, `record_run`, `fetch_all_deals` (M1/M2).
> - `scrapers/geocode.py` has `FakeGeocoder` (M2).
> - `scrapers/sources/reddit.py` has `def fetch(config: Config) -> list[RawDeal]` (M3).
> - `scrapers/run.py` already defines the `SOURCES` registry (reddit-only) and the canonical `run_all` (M3). The `main()` CLI entrypoint is added in M6. M5 only ADDS entries to `SOURCES`; it MUST NOT redefine `run_all`.
> - `config.toml` already has `[sources]` tables; M5 adds the `chains`/`slickdeals`/`local` sub-tables.

All commands are run from the repo root `/Users/jaehunb/projects/freemap`.

---

### Task 5.1: Record the `chains` offers-page fixture

**Files:** `tests/fixtures/chains_offers.html`

- [ ] **Step 1 — Create the recorded HTML fixture.** This is a static snapshot of a chain's "current offers" page. It contains one chain-wide BOGO offer that the scraper will expand to multiple Seattle branches (the branch list lives in config, not in this HTML). Write `tests/fixtures/chains_offers.html` exactly:

```html
<!DOCTYPE html>
<html lang="en">
<head><title>SeattleBeans Coffee — Current Offers</title></head>
<body>
  <main>
    <ul class="offers">
      <li class="offer" data-offer-id="bogo-latte-2026">
        <h3 class="offer-title">Buy One Get One Free Latte</h3>
        <p class="offer-desc">Buy any latte, get a second latte free. All Seattle locations. This week only.</p>
        <a class="offer-link" href="https://seattlebeans.example/offers/bogo-latte-2026">Details</a>
        <time class="offer-expires" datetime="2026-06-25T23:59:00">June 25, 2026</time>
      </li>
      <li class="offer" data-offer-id="free-cookie-2026">
        <h3 class="offer-title">Free Cookie With Any Drink</h3>
        <p class="offer-desc">Get one free cookie with the purchase of any drink. All Seattle locations.</p>
        <a class="offer-link" href="https://seattlebeans.example/offers/free-cookie-2026">Details</a>
        <time class="offer-expires" datetime="2026-07-02T23:59:00">July 2, 2026</time>
      </li>
    </ul>
  </main>
</body>
</html>
```

- [ ] **Step 2 — Commit the fixture.**

```bash
git add tests/fixtures/chains_offers.html
git commit -m "test(chains): add recorded offers-page fixture"
```

---

### Task 5.2: Add the `chains` config sub-table

**Files:** `config.toml`

- [ ] **Step 1 — Add the `[sources.chains]` table.** The scraper reads `config.sources["chains"]` for the offers URL and the Seattle branch list (`branches` maps a branch label to its geocodable address string — these flow into `RawDeal.raw_location` so the pipeline geocodes each branch). Append this block to `config.toml` (leave the existing `[meta]`, `[freshness]`, `[geocoder]`, `[sources.reddit]` content untouched):

```toml
[sources.chains]
offers_urls = ["https://seattlebeans.example/offers"]

[sources.chains.branches]
"Capitol Hill" = "1429 12th Ave, Seattle, WA 98122"
"Ballard" = "5402 22nd Ave NW, Seattle, WA 98107"
"Fremont" = "3501 Fremont Ave N, Seattle, WA 98103"
```

- [ ] **Step 2 — Verify `load_config` parses it (sanity check, no test file yet).**

```bash
python -c "from scrapers.config import load_config; c = load_config('config.toml'); print(c.sources['chains']['offers_urls']); print(c.sources['chains']['branches'])"
```

Expected output:

```
['https://seattlebeans.example/offers']
{'Capitol Hill': '1429 12th Ave, Seattle, WA 98122', 'Ballard': '5402 22nd Ave NW, Seattle, WA 98107', 'Fremont': '3501 Fremont Ave N, Seattle, WA 98103'}
```

- [ ] **Step 3 — Commit.**

```bash
git add config.toml
git commit -m "feat(config): add chains source settings (offers_urls + Seattle branches)"
```

---

### Task 5.3: Write the failing test for `chains.fetch`

**Files:** `tests/test_chains_source.py`

- [ ] **Step 1 — Write the full failing test.** It monkeypatches `httpx.get` to return the recorded fixture HTML (NEVER live network), builds a minimal `Config`, and asserts that the single BOGO offer is expanded to one `RawDeal` per branch with a per-branch unique `source_id` and the branch address in `raw_location`. Write `tests/test_chains_source.py`:

```python
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import chains

FIXTURE = Path(__file__).parent / "fixtures" / "chains_offers.html"


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["chains"],
        sources={
            "chains": {
                "offers_urls": ["https://seattlebeans.example/offers"],
                "branches": {
                    "Capitol Hill": "1429 12th Ave, Seattle, WA 98122",
                    "Ballard": "5402 22nd Ave NW, Seattle, WA 98107",
                    "Fremont": "3501 Fremont Ave N, Seattle, WA 98103",
                },
            }
        },
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_chains_fetch_expands_offers_to_branches(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = chains.fetch(_config())

    # 2 offers x 3 branches = 6 RawDeals
    assert len(deals) == 6
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "chains" for d in deals)

    # User-Agent from config was sent
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    # Every branch address shows up as raw_location
    locations = {d.raw_location for d in deals}
    assert locations == {
        "1429 12th Ave, Seattle, WA 98122",
        "5402 22nd Ave NW, Seattle, WA 98107",
        "3501 Fremont Ave N, Seattle, WA 98103",
    }

    # source_id is unique per (offer, branch) so upsert never collapses two branches
    ids = [d.source_id for d in deals]
    assert len(ids) == len(set(ids))

    # The BOGO offer's branch deals carry its title/url/expiry
    bogo = [d for d in deals if d.title == "Buy One Get One Free Latte"]
    assert len(bogo) == 3
    assert bogo[0].url == "https://seattlebeans.example/offers/bogo-latte-2026"
    assert bogo[0].expires_at is not None
    assert bogo[0].expires_at.year == 2026 and bogo[0].expires_at.month == 6
```

- [ ] **Step 2 — Run it, expect FAIL (module does not exist yet).**

```bash
pytest tests/test_chains_source.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.sources.chains'` (or `AttributeError: module ... has no attribute 'fetch'`).

- [ ] **Step 3 — Commit the failing test.**

```bash
git add tests/test_chains_source.py
git commit -m "test(chains): failing contract test for offers->branches expansion"
```

---

### Task 5.4: Implement `chains.fetch`

**Files:** `scrapers/sources/chains.py`

- [ ] **Step 1 — Write the full implementation.** Read `config.user_agent` for the HTTP header and `config.sources["chains"]` for the URLs + branch map. Parse the offers page with BeautifulSoup, then expand each offer across every configured branch (one `RawDeal` per offer-branch pair, with a composite `source_id`). Write `scrapers/sources/chains.py`:

```python
"""chains source: parse a chain's offers page and expand each offer to every
configured Seattle branch location (so a single chain-wide BOGO becomes one
physical RawDeal per branch). Reads config.user_agent and config.sources["chains"]."""

from __future__ import annotations

from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from scrapers.config import Config
from scrapers.contract import RawDeal


def _parse_expires(time_el) -> datetime | None:
    if time_el is None:
        return None
    raw = time_el.get("datetime") or time_el.get_text(strip=True)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("chains", {})
    offers_urls: list[str] = settings.get("offers_urls", [])
    branches: dict = settings.get("branches", {})
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in offers_urls:
        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for offer in soup.select("li.offer"):
            offer_id = offer.get("data-offer-id") or ""
            title_el = offer.select_one(".offer-title")
            desc_el = offer.select_one(".offer-desc")
            link_el = offer.select_one(".offer-link")
            expires_el = offer.select_one(".offer-expires")

            title = title_el.get_text(strip=True) if title_el else ""
            description = desc_el.get_text(strip=True) if desc_el else None
            offer_url = link_el.get("href") if link_el else url
            expires_at = _parse_expires(expires_el)

            for branch_name, branch_address in branches.items():
                # Composite id keeps each branch a distinct upsert row.
                source_id = f"{offer_id}::{branch_name}"
                deals.append(
                    RawDeal(
                        source="chains",
                        source_id=source_id,
                        title=title,
                        url=offer_url,
                        description=description,
                        raw_location=branch_address,
                        posted_at=None,
                        expires_at=expires_at,
                        raw={
                            "offer_id": offer_id,
                            "branch": branch_name,
                            "offers_url": url,
                        },
                    )
                )
    return deals
```

- [ ] **Step 2 — Run the test, expect PASS.**

```bash
pytest tests/test_chains_source.py -v
```

Expected: PASS, 1 passed.

- [ ] **Step 3 — Commit.**

```bash
git add scrapers/sources/chains.py
git commit -m "feat(chains): expand offers page to per-branch physical RawDeals"
```

---

### Task 5.5: Register `chains` in the `run.py` SOURCES registry

**Files:** `scrapers/run.py`

- [ ] **Step 1 — Add the import.** In `scrapers/run.py`, the imports already pull in `reddit` from `scrapers.sources`. Add `chains` alongside it. Find the existing import line:

```python
from scrapers.sources import reddit
```

and replace it with:

```python
from scrapers.sources import reddit, chains
```

- [ ] **Step 2 — Add `chains` to the registry.** Find the existing `SOURCES` registry (it currently holds only the reddit entry from M3):

```python
SOURCES: dict[str, callable] = {"reddit": reddit.fetch}
```

and replace it with:

```python
SOURCES: dict[str, callable] = {"reddit": reddit.fetch, "chains": chains.fetch}
```

> Do NOT change `run_all` or `main` — only the import and the `SOURCES` dict.

- [ ] **Step 2b — Verify the registry change with one-line check.**

```bash
python -c "from scrapers.run import SOURCES; print(sorted(SOURCES))"
```

Expected output:

```
['chains', 'reddit']
```

- [ ] **Step 3 — Commit.**

```bash
git add scrapers/run.py
git commit -m "feat(run): register chains in SOURCES registry"
```

---

### Task 5.6: Record the `slickdeals` deals-list fixture

**Files:** `tests/fixtures/slickdeals_list.html`

- [ ] **Step 1 — Create the recorded HTML fixture.** A snapshot of a deals-list page; most entries are online-only (no location), one has a physical store location to exercise the physical path. Write `tests/fixtures/slickdeals_list.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><title>Slickdeals — Free & BOGO</title></head>
<body>
  <div class="deal-list">
    <article class="deal" data-deal-id="sd-100001">
      <h2 class="deal-title">Free Audiobook Download (New Members)</h2>
      <p class="deal-summary">Get one free audiobook when you sign up. Online only.</p>
      <a class="deal-url" href="https://slickdeals.example/f/100001-free-audiobook">See deal</a>
    </article>
    <article class="deal" data-deal-id="sd-100002">
      <h2 class="deal-title">Buy One Get One Free eBook</h2>
      <p class="deal-summary">BOGO on select eBooks this weekend. Online only.</p>
      <a class="deal-url" href="https://slickdeals.example/f/100002-bogo-ebook">See deal</a>
    </article>
    <article class="deal" data-deal-id="sd-100003">
      <h2 class="deal-title">Free Coffee at Downtown Seattle Store</h2>
      <p class="deal-summary">Free 12oz coffee, in store only.</p>
      <a class="deal-url" href="https://slickdeals.example/f/100003-free-coffee">See deal</a>
      <span class="deal-location">1518 6th Ave, Seattle, WA 98101</span>
    </article>
  </div>
</body>
</html>
```

- [ ] **Step 2 — Commit.**

```bash
git add tests/fixtures/slickdeals_list.html
git commit -m "test(slickdeals): add recorded deals-list fixture"
```

---

### Task 5.7: Add the `slickdeals` config sub-table

**Files:** `config.toml`

- [ ] **Step 1 — Append `[sources.slickdeals]`** to `config.toml` (the scraper reads `config.sources["slickdeals"]["listing_urls"]`):

```toml
[sources.slickdeals]
listing_urls = ["https://slickdeals.example/deals/free"]
```

- [ ] **Step 2 — Verify.**

```bash
python -c "from scrapers.config import load_config; print(load_config('config.toml').sources['slickdeals']['listing_urls'])"
```

Expected output:

```
['https://slickdeals.example/deals/free']
```

- [ ] **Step 3 — Commit.**

```bash
git add config.toml
git commit -m "feat(config): add slickdeals source settings (listing_urls)"
```

---

### Task 5.8: Write the failing test for `slickdeals.fetch`

**Files:** `tests/test_slickdeals_source.py`

- [ ] **Step 1 — Write the full failing test.** Monkeypatch `httpx.get` to return the fixture HTML; assert three `RawDeal`s, two with `raw_location=None` (online) and one with the store address (so the pipeline later marks it physical). Write `tests/test_slickdeals_source.py`:

```python
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import slickdeals

FIXTURE = Path(__file__).parent / "fixtures" / "slickdeals_list.html"


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["slickdeals"],
        sources={"slickdeals": {"listing_urls": ["https://slickdeals.example/deals/free"]}},
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_slickdeals_fetch_parses_list(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(html)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = slickdeals.fetch(_config())

    assert len(deals) == 3
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "slickdeals" for d in deals)
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    by_id = {d.source_id: d for d in deals}
    assert set(by_id) == {"sd-100001", "sd-100002", "sd-100003"}

    # Two online-only deals -> raw_location None
    assert by_id["sd-100001"].raw_location is None
    assert by_id["sd-100002"].raw_location is None
    assert by_id["sd-100001"].url == "https://slickdeals.example/f/100001-free-audiobook"

    # One physical deal carries the store address
    assert by_id["sd-100003"].raw_location == "1518 6th Ave, Seattle, WA 98101"
    assert by_id["sd-100003"].title == "Free Coffee at Downtown Seattle Store"
```

- [ ] **Step 2 — Run it, expect FAIL.**

```bash
pytest tests/test_slickdeals_source.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.sources.slickdeals'`.

- [ ] **Step 3 — Commit the failing test.**

```bash
git add tests/test_slickdeals_source.py
git commit -m "test(slickdeals): failing contract test for deals-list parsing"
```

---

### Task 5.9: Implement `slickdeals.fetch`

**Files:** `scrapers/sources/slickdeals.py`

- [ ] **Step 1 — Write the full implementation.** Parse each `article.deal`; the optional `.deal-location` span becomes `raw_location` (absent → `None`, which the pipeline classifies as online). Write `scrapers/sources/slickdeals.py`:

```python
"""slickdeals source: parse a recorded deals-list page. Most deals are online-only
(no location); a deal-location span marks the occasional physical deal. Reads
config.user_agent and config.sources["slickdeals"]["listing_urls"]."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from scrapers.config import Config
from scrapers.contract import RawDeal


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("slickdeals", {})
    listing_urls: list[str] = settings.get("listing_urls", [])
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in listing_urls:
        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for art in soup.select("article.deal"):
            deal_id = art.get("data-deal-id") or ""
            title_el = art.select_one(".deal-title")
            summary_el = art.select_one(".deal-summary")
            url_el = art.select_one(".deal-url")
            location_el = art.select_one(".deal-location")

            title = title_el.get_text(strip=True) if title_el else ""
            description = summary_el.get_text(strip=True) if summary_el else None
            deal_url = url_el.get("href") if url_el else url
            raw_location = location_el.get_text(strip=True) if location_el else None

            deals.append(
                RawDeal(
                    source="slickdeals",
                    source_id=deal_id,
                    title=title,
                    url=deal_url,
                    description=description,
                    raw_location=raw_location,
                    posted_at=None,
                    expires_at=None,
                    raw={"deal_id": deal_id, "listing_url": url},
                )
            )
    return deals
```

- [ ] **Step 2 — Run the test, expect PASS.**

```bash
pytest tests/test_slickdeals_source.py -v
```

Expected: PASS, 1 passed.

- [ ] **Step 3 — Commit.**

```bash
git add scrapers/sources/slickdeals.py
git commit -m "feat(slickdeals): parse deals-list into online + physical RawDeals"
```

---

### Task 5.10: Register `slickdeals` in the `run.py` SOURCES registry

**Files:** `scrapers/run.py`

- [ ] **Step 1 — Extend the import.** Find:

```python
from scrapers.sources import reddit, chains
```

and replace it with:

```python
from scrapers.sources import reddit, chains, slickdeals
```

- [ ] **Step 2 — Add to the registry.** Find:

```python
SOURCES: dict[str, callable] = {"reddit": reddit.fetch, "chains": chains.fetch}
```

and replace it with:

```python
SOURCES: dict[str, callable] = {
    "reddit": reddit.fetch,
    "chains": chains.fetch,
    "slickdeals": slickdeals.fetch,
}
```

- [ ] **Step 2b — Verify.**

```bash
python -c "from scrapers.run import SOURCES; print(sorted(SOURCES))"
```

Expected output:

```
['chains', 'reddit', 'slickdeals']
```

- [ ] **Step 3 — Commit.**

```bash
git add scrapers/run.py
git commit -m "feat(run): register slickdeals in SOURCES registry"
```

---

### Task 5.11: Record the `local` feed fixture

**Files:** `tests/fixtures/local_feed.xml`

- [ ] **Step 1 — Create the recorded XML feed.** An RSS-style feed of local Seattle deals; each item is a physical deal whose neighborhood/address goes into `raw_location`. Write `tests/fixtures/local_feed.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Seattle Local Deals</title>
    <link>https://localdeals.example/seattle</link>
    <item>
      <guid>local-2026-0001</guid>
      <title>Free Scoop Day at Capitol Hill Creamery</title>
      <description>One free scoop per visitor, all day. Capitol Hill.</description>
      <link>https://localdeals.example/seattle/0001-free-scoop</link>
      <location>Capitol Hill, Seattle, WA</location>
      <pubDate>Mon, 15 Jun 2026 09:00:00 -0700</pubDate>
    </item>
    <item>
      <guid>local-2026-0002</guid>
      <title>BOGO Slice at Ballard Pizza Co</title>
      <description>Buy one slice, get one free, 4-6pm.</description>
      <link>https://localdeals.example/seattle/0002-bogo-slice</link>
      <location>5440 Ballard Ave NW, Seattle, WA 98107</location>
      <pubDate>Tue, 16 Jun 2026 12:00:00 -0700</pubDate>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2 — Commit.**

```bash
git add tests/fixtures/local_feed.xml
git commit -m "test(local): add recorded local feed fixture"
```

---

### Task 5.12: Add the `local` config sub-table

**Files:** `config.toml`

- [ ] **Step 1 — Append `[sources.local]`** to `config.toml` (the scraper reads `config.sources["local"]["feed_urls"]`):

```toml
[sources.local]
feed_urls = ["https://localdeals.example/seattle/feed.xml"]
```

- [ ] **Step 2 — Verify.**

```bash
python -c "from scrapers.config import load_config; print(load_config('config.toml').sources['local']['feed_urls'])"
```

Expected output:

```
['https://localdeals.example/seattle/feed.xml']
```

- [ ] **Step 3 — Commit.**

```bash
git add config.toml
git commit -m "feat(config): add local source settings (feed_urls)"
```

---

### Task 5.13: Write the failing test for `local.fetch`

**Files:** `tests/test_local_source.py`

- [ ] **Step 1 — Write the full failing test.** Monkeypatch `httpx.get` to return the fixture XML; assert two physical `RawDeal`s with location text and a parsed `posted_at`. Write `tests/test_local_source.py`:

```python
from pathlib import Path

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.sources import local

FIXTURE = Path(__file__).parent / "fixtures" / "local_feed.xml"


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["local"],
        sources={"local": {"feed_urls": ["https://localdeals.example/seattle/feed.xml"]}},
    )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def test_local_fetch_parses_feed(monkeypatch):
    xml = FIXTURE.read_text(encoding="utf-8")
    captured = {}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return _FakeResponse(xml)

    monkeypatch.setattr(httpx, "get", fake_get)

    deals = local.fetch(_config())

    assert len(deals) == 2
    assert all(isinstance(d, RawDeal) for d in deals)
    assert all(d.source == "local" for d in deals)
    assert captured["headers"]["User-Agent"] == "FreeMapSeattle/1.0 (test)"

    by_id = {d.source_id: d for d in deals}
    assert set(by_id) == {"local-2026-0001", "local-2026-0002"}

    # All local deals are physical -> raw_location populated
    assert by_id["local-2026-0001"].raw_location == "Capitol Hill, Seattle, WA"
    assert by_id["local-2026-0002"].raw_location == "5440 Ballard Ave NW, Seattle, WA 98107"
    assert by_id["local-2026-0001"].url == "https://localdeals.example/seattle/0001-free-scoop"

    # pubDate parsed into posted_at
    assert by_id["local-2026-0001"].posted_at is not None
    assert by_id["local-2026-0001"].posted_at.year == 2026
    assert by_id["local-2026-0001"].posted_at.month == 6
    assert by_id["local-2026-0001"].posted_at.day == 15
```

- [ ] **Step 2 — Run it, expect FAIL.**

```bash
pytest tests/test_local_source.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.sources.local'`.

- [ ] **Step 3 — Commit the failing test.**

```bash
git add tests/test_local_source.py
git commit -m "test(local): failing contract test for local feed parsing"
```

---

### Task 5.14: Implement `local.fetch`

**Files:** `scrapers/sources/local.py`

- [ ] **Step 1 — Write the full implementation.** Parse the RSS feed with the stdlib `xml.etree.ElementTree` (no third-party XML dependency — BeautifulSoup's `features="xml"` would require `lxml`, which is NOT in the pinned deps, and `html.parser` lowercases tags and mishandles void `<link>` elements in RSS). `ElementTree` preserves exact tag casing (`pubDate`, `guid`) and reads `<link>` text correctly. Each `<item>` becomes one physical `RawDeal`; `<pubDate>` (RFC-822) is parsed via stdlib `email.utils.parsedate_to_datetime`, defensively (bad date → `None`, never raises). A malformed feed body is caught so one bad feed never aborts the others. Write `scrapers/sources/local.py`:

```python
"""local source: parse a recorded local-deals RSS feed into physical RawDeals.
Each item carries a Seattle location, so the pipeline classifies these as physical.
Reads config.user_agent and config.sources["local"]["feed_urls"]."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal


def _parse_pubdate(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None


def _text(item: ET.Element, tag: str) -> str | None:
    """Return the stripped text of <item>'s child <tag>, or None if absent/empty."""
    el = item.find(tag)
    if el is None or el.text is None:
        return None
    value = el.text.strip()
    return value or None


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("local", {})
    feed_urls: list[str] = settings.get("feed_urls", [])
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in feed_urls:
        resp = httpx.get(url, headers=headers, timeout=30.0)
        resp.raise_for_status()
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            # A malformed feed never aborts the run; skip it.
            continue

        for item in root.iter("item"):
            guid = _text(item, "guid") or ""
            title = _text(item, "title") or ""
            description = _text(item, "description")
            link = _text(item, "link") or url
            raw_location = _text(item, "location")
            posted_at = _parse_pubdate(_text(item, "pubDate"))

            deals.append(
                RawDeal(
                    source="local",
                    source_id=guid,
                    title=title,
                    url=link,
                    description=description,
                    raw_location=raw_location,
                    posted_at=posted_at,
                    expires_at=None,
                    raw={"guid": guid, "feed_url": url},
                )
            )
    return deals
```

- [ ] **Step 2 — Run the test, expect PASS.**

```bash
pytest tests/test_local_source.py -v
```

Expected: PASS, 1 passed. (`ElementTree` reads `<guid>`, `<pubDate>`, `<location>`, and `<link>` with exact casing, so `raw_location`, `posted_at`, and `url` populate correctly with no third-party XML dependency.)

- [ ] **Step 3 — Commit.**

```bash
git add scrapers/sources/local.py
git commit -m "feat(local): parse local RSS feed into physical RawDeals"
```

---

### Task 5.15: Register `local` in the `run.py` SOURCES registry

**Files:** `scrapers/run.py`

- [ ] **Step 1 — Extend the import.** Find:

```python
from scrapers.sources import reddit, chains, slickdeals
```

and replace it with:

```python
from scrapers.sources import reddit, chains, slickdeals, local
```

- [ ] **Step 2 — Complete the registry.** Find:

```python
SOURCES: dict[str, callable] = {
    "reddit": reddit.fetch,
    "chains": chains.fetch,
    "slickdeals": slickdeals.fetch,
}
```

and replace it with:

```python
SOURCES: dict[str, callable] = {
    "reddit": reddit.fetch,
    "chains": chains.fetch,
    "slickdeals": slickdeals.fetch,
    "local": local.fetch,
}
```

- [ ] **Step 2b — Verify all four registered.**

```bash
python -c "from scrapers.run import SOURCES; print(sorted(SOURCES))"
```

Expected output:

```
['chains', 'local', 'reddit', 'slickdeals']
```

- [ ] **Step 3 — Commit.**

```bash
git add scrapers/run.py
git commit -m "feat(run): register local in SOURCES registry (all 4 sources wired)"
```

---

### Task 5.16: Write the failing four-source resilience test for `run_all`

**Files:** `tests/test_run_all_sources.py`

- [ ] **Step 1 — Write the full failing test.** This drives the canonical `run_all(config, conn, geocoder, now, sources=...)` over all four sources, injecting a custom `sources` dict where one source deliberately throws. It asserts: (a) the throwing source is recorded with an error and 0 upserted, (b) the other three still upsert their rows, and (c) `run_all` returns the canonical `{name: {"deals_found", "upserted", "errors"}}` shape. The injected `sources` dict reuses the real `SOURCES` callables for the survivors so this is a true integration over the real pipeline + `FakeGeocoder`. Write `tests/test_run_all_sources.py`:

```python
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from scrapers.config import Config
from scrapers.db import connect, init_db, fetch_all_deals
from scrapers.geocode import FakeGeocoder
from scrapers.run import SOURCES, run_all

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 6, 18, 12, 0, 0)


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


def _config() -> Config:
    return Config(
        metro="seattle",
        db_path=":memory:",
        stale_after_hours=24,
        user_agent="FreeMapSeattle/1.0 (test)",
        geocoder_min_interval_seconds=1.0,
        geocoder_max_live_calls=200,
        sources_enabled=["reddit", "chains", "slickdeals", "local"],
        sources={
            "reddit": {"subreddits": ["seattle"], "listing_urls": ["https://reddit.example/r/seattle.json"]},
            "chains": {
                "offers_urls": ["https://seattlebeans.example/offers"],
                "branches": {
                    "Capitol Hill": "1429 12th Ave, Seattle, WA 98122",
                    "Ballard": "5402 22nd Ave NW, Seattle, WA 98107",
                    "Fremont": "3501 Fremont Ave N, Seattle, WA 98103",
                },
            },
            "slickdeals": {"listing_urls": ["https://slickdeals.example/deals/free"]},
            "local": {"feed_urls": ["https://localdeals.example/seattle/feed.xml"]},
        },
    )


def _fixture_router():
    """Return an httpx.get replacement that serves the right recorded payload by URL."""
    chains_html = (FIX / "chains_offers.html").read_text(encoding="utf-8")
    slickdeals_html = (FIX / "slickdeals_list.html").read_text(encoding="utf-8")
    local_xml = (FIX / "local_feed.xml").read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        if "seattlebeans" in url:
            return _FakeResponse(chains_html)
        if "slickdeals" in url:
            return _FakeResponse(slickdeals_html)
        if "localdeals" in url:
            return _FakeResponse(local_xml)
        raise AssertionError(f"unexpected URL in test: {url}")

    return fake_get


def test_run_all_one_source_throws_others_still_upsert(monkeypatch):
    monkeypatch.setattr(httpx, "get", _fixture_router())

    conn = connect(":memory:")
    init_db(conn)

    # Geocode every address/neighborhood the fixtures use so physical deals geocode "ok".
    geocoder = FakeGeocoder(
        {
            "1429 12th Ave, Seattle, WA 98122": (47.6097, -122.3160),
            "5402 22nd Ave NW, Seattle, WA 98107": (47.6680, -122.3850),
            "3501 Fremont Ave N, Seattle, WA 98103": (47.6510, -122.3500),
            "1518 6th Ave, Seattle, WA 98101": (47.6110, -122.3370),
            "Capitol Hill, Seattle, WA": (47.6253, -122.3222),
            "5440 Ballard Ave NW, Seattle, WA 98107": (47.6670, -122.3830),
        }
    )

    def boom(config):
        raise RuntimeError("reddit source exploded")

    # Inject: reddit deliberately throws; the other three use the real fetchers.
    injected = {
        "reddit": boom,
        "chains": SOURCES["chains"],
        "slickdeals": SOURCES["slickdeals"],
        "local": SOURCES["local"],
    }

    summary = run_all(_config(), conn, geocoder, NOW, sources=injected)

    # Canonical return shape: one entry per source with the three keys.
    assert set(summary) == {"reddit", "chains", "slickdeals", "local"}
    for entry in summary.values():
        assert set(entry) == {"deals_found", "upserted", "errors"}

    # The throwing source is recorded as errored, 0 upserted — never aborts the run.
    assert summary["reddit"]["errors"] is not None
    assert "exploded" in summary["reddit"]["errors"]
    assert summary["reddit"]["upserted"] == 0

    # The three healthy sources upserted their rows (chains expands 2 offers x 3 branches).
    assert summary["chains"]["errors"] is None
    assert summary["chains"]["upserted"] == 6
    assert summary["slickdeals"]["errors"] is None
    assert summary["slickdeals"]["upserted"] == 3
    assert summary["local"]["errors"] is None
    assert summary["local"]["upserted"] == 2

    # DB holds exactly the survivors' rows: 6 + 3 + 2 = 11, none from reddit.
    rows = fetch_all_deals(conn)
    assert len(rows) == 11
    assert all(r["source"] != "reddit" for r in rows)
```

- [ ] **Step 2 — Run it, expect FAIL.** Because every real source module + the four-entry `SOURCES` registry now exist, this fails only on the integration assertions, not on imports — most likely the survivor-upsert counts if any wiring is off. Run:

```bash
pytest tests/test_run_all_sources.py -v
```

Expected at this point: PASS *if* M3's `run_all` already implements the canonical try/except-per-source + `record_run` contract (it does, per the M3 interface). If it FAILS, the failure message localizes the gap (e.g. an `upserted` count mismatch). Do NOT edit `run_all` — it is owned by M3 and frozen; instead fix the offending M5 source/config/fixture so the survivors upsert their expected counts, then re-run until PASS.

- [ ] **Step 3 — Commit the test.**

```bash
git add tests/test_run_all_sources.py
git commit -m "test(run): all-4-sources run_all stays up when one source throws"
```

---

### Task 5.17: Full-suite regression + milestone close-out

**Files:** _(none — verification only)_

- [ ] **Step 1 — Run the entire test suite** to confirm the three new sources, the registry edits, and the resilience test all pass alongside M1-M4 tests:

```bash
pytest -q
```

Expected: all tests pass (0 failed), including `test_chains_source.py`, `test_slickdeals_source.py`, `test_local_source.py`, and `test_run_all_sources.py`.

- [ ] **Step 2 — Confirm no `NotImplementedError` stubs survived** (M2 should already have replaced `run_pipeline` and `fetch_all_deals`; this guards against a regression introduced while wiring sources):

```bash
grep -rn "NotImplementedError" scrapers/ api/ || echo "OK: no stubs remain"
```

Expected output: `OK: no stubs remain`.

- [ ] **Step 3 — Confirm `run_all` was not redefined or duplicated in M5** (it must remain the single M3 definition):

```bash
grep -rn "def run_all" scrapers/run.py
```

Expected output: exactly one line — `def run_all(config: Config, conn, geocoder, now, sources: dict | None = None) -> dict[str, dict]:`.

- [ ] **Step 4 — End-state commit** (records the milestone as complete; all four sources are now behind the proven pipeline and the single canonical `run_all`):

```bash
git commit --allow-empty -m "chore(m5): all 4 sources wired behind shared pipeline + run_all"
```

**End state:** `chains`, `slickdeals`, and `local` each expose `fetch(config: Config) -> list[RawDeal]`, are tested only against the canonical recorded fixtures (`tests/fixtures/chains_offers.html`, `slickdeals_list.html`, `local_feed.xml`) via monkeypatched `httpx.get`, and are registered in the existing `run.py` `SOURCES` registry. A four-source `run_all` proves that one throwing source is recorded as errored without aborting the other three. `run_all` remains the untouched M3 canonical definition (the `main()` entrypoint is still added in M6).

---

I have the full spec. Now I'll output the complete Milestone 6 markdown using the canonical interfaces verbatim.

## Milestone 6: TASK.md + MeshClaw handoff

**Goal:** Make `python -m scrapers.run` the single unattended, offline-testable entrypoint (already-specified `main()` calling the existing `run_all`), then write `TASK.md` (the MeshClaw run spec) and `README.md`, with offline tests that prove `--help` works and a full fixture-backed run populates the DB and writes one `scrape_runs` row per source.

> Prerequisite: Milestones 1–5 are complete. `scrapers/run.py` already defines the module-level `SOURCES` registry (all four sources, wired across M3+M5) and `run_all(config, conn, geocoder, now, sources=None) -> dict[str, dict]`, but does NOT yet define `main()` — this milestone adds it. `scrapers/config.py` defines `load_config`. `scrapers/db.py` defines `connect`, `init_db`, `record_run`. `scrapers/geocode.py` defines `Geocoder` and `FakeGeocoder`. The four canonical fixtures (`tests/fixtures/reddit_sample.json`, `tests/fixtures/chains_offers.html`, `tests/fixtures/slickdeals_list.html`, `tests/fixtures/local_feed.xml`) exist and each `scrapers/sources/X.py` `fetch()` parses its fixture when `httpx.get` is monkeypatched. This milestone only adds `main()`, two offline tests, `TASK.md`, and `README.md`. No function may remain `NotImplementedError` after this milestone (they were all replaced in Milestone 2).

---

### Task 6.1: Add `main()` argparse entrypoint to `scrapers/run.py`

Implement the canonical `def main(argv=None) -> int` exactly as specified: argparse `--db`/`--config`, `load_config`, `connect`, `init_db`, build `Geocoder`, `now=datetime.now()`, call the existing `run_all(...)`, print a per-source summary from the returned dict, and return exit code 0 if at least one source succeeded with no exception, 1 only if every source errored.

**Files:** `scrapers/run.py`

- [ ] **Step 1 — Read the current top of `scrapers/run.py`** to see the existing imports, the `SOURCES` registry, and `run_all`. Run:

  ```bash
  sed -n '1,40p' /Users/jaehunb/projects/freemap/scrapers/run.py
  ```

  Expected: you see `import` lines, `SOURCES: dict[str, callable] = {...}`, and `def run_all(config, conn, geocoder, now, sources=None) -> dict[str, dict]:`. Confirm there is currently **no** `def main(`. Run:

  ```bash
  grep -n "def main\|^import\|^from\|argparse\|datetime\|Geocoder\|load_config\|init_db\|^def connect\|from .db\|from .config\|from .geocode" /Users/jaehunb/projects/freemap/scrapers/run.py
  ```

  Expected: shows the existing imports; `def main(` is absent. (If `argparse`, `datetime`, `load_config`, `connect`, `init_db`, or `Geocoder` are already imported, do NOT re-import them in Step 3 — reuse the existing import lines.)

- [ ] **Step 2 — Write the failing test for `--help` first** (drives the existence of `main`). Create `/Users/jaehunb/projects/freemap/tests/test_run_main.py`:

  ```python
  import subprocess
  import sys


  def test_help_exits_zero():
      """`python -m scrapers.run --help` must exit 0 and mention --db/--config."""
      result = subprocess.run(
          [sys.executable, "-m", "scrapers.run", "--help"],
          cwd="/Users/jaehunb/projects/freemap",
          capture_output=True,
          text=True,
      )
      assert result.returncode == 0, result.stderr
      assert "--db" in result.stdout
      assert "--config" in result.stdout
  ```

- [ ] **Step 3 — Run the test, expect FAIL.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_run_main.py::test_help_exits_zero -v
  ```

  Expected: FAIL. Because `scrapers/run.py` has no `if __name__ == "__main__"` block and no `main()`, `python -m scrapers.run --help` does not register `--help`/`--db`/`--config`, so the assertion `result.returncode == 0` (or the `--db` substring assertion) fails.

- [ ] **Step 4 — Add the imports `main()` needs at the top of `scrapers/run.py`.** Only add lines that are NOT already present (per Step 1). Insert these immediately after the existing `import`/`from` block:

  ```python
  import argparse
  from datetime import datetime

  from .config import load_config
  from .db import connect, init_db
  from .geocode import Geocoder
  ```

  (If any of these already exist in the file, skip that specific line — do not duplicate imports.)

- [ ] **Step 5 — Append the full `main()` implementation** to the END of `scrapers/run.py` (after `run_all`). Use this exact code:

  ```python
  def main(argv=None) -> int:
      parser = argparse.ArgumentParser(
          prog="scrapers.run",
          description="FreeMap scrape entrypoint: run all enabled sources through the pipeline into SQLite.",
      )
      parser.add_argument(
          "--db",
          default=None,
          help="Path to the SQLite DB (overrides config.db_path).",
      )
      parser.add_argument(
          "--config",
          default="config.toml",
          help="Path to config.toml (default: config.toml).",
      )
      args = parser.parse_args(argv)

      config = load_config(args.config)
      db_path = args.db if args.db is not None else config.db_path

      conn = connect(db_path)
      init_db(conn)

      geocoder = Geocoder(
          conn,
          user_agent=config.user_agent,
          min_interval_seconds=config.geocoder_min_interval_seconds,
          max_live_calls=config.geocoder_max_live_calls,
      )

      now = datetime.now()
      summary = run_all(config, conn, geocoder, now)

      print(f"FreeMap scrape — metro={config.metro} db={db_path} at {now.isoformat()}")
      any_success = False
      for name, result in summary.items():
          deals_found = result["deals_found"]
          upserted = result["upserted"]
          errors = result["errors"]
          if errors is None:
              any_success = True
              flag = " [0 FOUND]" if deals_found == 0 else ""
              print(f"  {name}: found={deals_found} upserted={upserted} ok{flag}")
          else:
              print(f"  {name}: found={deals_found} upserted={upserted} ERROR: {errors}")

      conn.close()
      return 0 if any_success else 1


  if __name__ == "__main__":
      raise SystemExit(main())
  ```

- [ ] **Step 6 — Run the `--help` test, expect PASS.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_run_main.py::test_help_exits_zero -v
  ```

  Expected: PASS, 1 passed. (`python -m scrapers.run --help` now exits 0 and prints the `--db` and `--config` options.)

- [ ] **Step 7 — Commit.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && git add scrapers/run.py tests/test_run_main.py && git commit -m "feat(run): add main() argparse entrypoint for python -m scrapers.run"
  ```

  Expected: one commit created.

---

### Task 6.2: Offline full-run test — fixtures + FakeGeocoder populate the DB and write one `scrape_runs` row per source

Add a second test to `tests/test_run_main.py` that calls `main()` in-process against a temp DB and config, with `httpx.get` monkeypatched to serve the four canonical fixtures by URL and `Geocoder` monkeypatched to a `FakeGeocoder` (so NO live network and NO live Nominatim). Assert the DB gains deals, that `scrape_runs` has exactly one row per enabled source for this run, and that the exit code is 0.

**Files:** `tests/test_run_main.py`, `tests/conftest.py` (read only)

- [ ] **Step 1 — Confirm the four canonical fixtures exist** (created in M3 + M5). Run:

  ```bash
  ls /Users/jaehunb/projects/freemap/tests/fixtures/
  ```

  Expected: the listing includes `reddit_sample.json`, `chains_offers.html`, `slickdeals_list.html`, and `local_feed.xml`. The per-source config keys are fixed by the canonical contract — `reddit` and `slickdeals` read `listing_urls`, `chains` reads `offers_urls` (+ `[sources.chains.branches]`), `local` reads `feed_urls`; `user_agent`/`sources_enabled` live under `[meta]`. The temp `config.toml` in Step 3 sets those keys and the fake `httpx.get` in Step 4 maps each URL to its fixture.

- [ ] **Step 2 — Read the existing `conftest.py`** so the new test reuses (not re-invents) any fixture-loading helper. Run:

  ```bash
  cat /Users/jaehunb/projects/freemap/tests/conftest.py
  ```

  Expected: you see how earlier milestones load fixtures (e.g. a `fixtures` path helper). The test below is self-contained and reads fixture files directly via the `tests/fixtures/` path, so it works regardless — but if a `fixture_path`/`load_fixture` helper exists, prefer importing it instead of the inline `_FIXTURES_DIR` constant.

- [ ] **Step 3 — Add the offline full-run test** to the END of `/Users/jaehunb/projects/freemap/tests/test_run_main.py`. This builds a temp `config.toml` enabling all four sources (with URLs that map 1:1 to the fixtures), monkeypatches `httpx.get` to serve fixture bytes by URL, and monkeypatches `scrapers.run.Geocoder` to a `FakeGeocoder`:

  ```python
  import os
  from pathlib import Path

  import httpx
  import pytest

  import scrapers.run as run_module
  from scrapers.geocode import FakeGeocoder

  _FIXTURES_DIR = Path(__file__).parent / "fixtures"

  # URL -> fixture filename. The temp config.toml below sets these exact URLs so
  # each source's httpx.get(url) is served the matching recorded payload.
  _URL_TO_FIXTURE = {
      "https://test.local/reddit": "reddit_sample.json",
      "https://test.local/chains": "chains_offers.html",
      "https://test.local/slickdeals": "slickdeals_list.html",
      "https://test.local/local": "local_feed.xml",
  }


  class _FakeResponse:
      def __init__(self, body: bytes):
          self._body = body
          self.status_code = 200

      @property
      def text(self) -> str:
          return self._body.decode("utf-8")

      @property
      def content(self) -> bytes:
          return self._body

      def json(self):
          import json

          return json.loads(self._body.decode("utf-8"))

      def raise_for_status(self):
          return None


  def _fake_httpx_get(url, *args, **kwargs):
      for prefix, filename in _URL_TO_FIXTURE.items():
          if url.startswith(prefix):
              body = (_FIXTURES_DIR / filename).read_bytes()
              return _FakeResponse(body)
      raise AssertionError(f"Unexpected live URL in offline test: {url}")


  _CONFIG_TOML = """
  [meta]
  metro = "seattle"
  db_path = "PLACEHOLDER_DB"
  user_agent = "FreeMapTest/1.0 (offline-test)"
  sources_enabled = ["reddit", "chains", "slickdeals", "local"]

  [freshness]
  stale_after_hours = 24

  [geocoder]
  min_interval_seconds = 0.0
  max_live_calls = 0

  [sources.reddit]
  subreddits = ["seattle"]
  listing_urls = ["https://test.local/reddit"]

  [sources.chains]
  offers_urls = ["https://test.local/chains"]

  [sources.chains.branches]
  "Capitol Hill" = "Capitol Hill, Seattle"

  [sources.slickdeals]
  listing_urls = ["https://test.local/slickdeals"]

  [sources.local]
  feed_urls = ["https://test.local/local"]
  """


  def test_full_offline_run_populates_db_and_scrape_runs(tmp_path, monkeypatch):
      """main() over the four recorded fixtures fills `deals` and writes one
      `scrape_runs` row per enabled source, with exit code 0 — no network."""
      db_file = tmp_path / "deals.db"
      config_file = tmp_path / "config.toml"
      config_file.write_text(_CONFIG_TOML.replace("PLACEHOLDER_DB", str(db_file)))

      # No live network: every source's httpx.get is served a recorded fixture.
      monkeypatch.setattr(httpx, "get", _fake_httpx_get)

      # No live Nominatim: replace the Geocoder main() constructs with a
      # FakeGeocoder. Any Seattle-ish raw_location resolves; misses -> None.
      class _PatchedGeocoder:
          def __init__(self, *args, **kwargs):
              self._fake = FakeGeocoder(
                  {
                      "Capitol Hill": (47.6253, -122.3222),
                      "Capitol Hill, Seattle": (47.6253, -122.3222),
                      "Downtown Seattle": (47.6062, -122.3321),
                      "Ballard": (47.6685, -122.3838),
                  }
              )

          def geocode(self, raw_location):
              return self._fake.geocode(raw_location)

      monkeypatch.setattr(run_module, "Geocoder", _PatchedGeocoder)

      exit_code = run_module.main(["--config", str(config_file), "--db", str(db_file)])

      # At least one source ran cleanly -> exit 0.
      assert exit_code == 0

      # DB exists and has rows.
      assert db_file.exists()
      from scrapers.db import connect

      conn = connect(str(db_file))
      deal_count = conn.execute("SELECT COUNT(*) AS c FROM deals").fetchone()["c"]
      assert deal_count > 0, "expected the offline fixtures to produce >=1 deal"

      # Exactly one scrape_runs row per enabled source for this run.
      rows = conn.execute(
          "SELECT source FROM scrape_runs ORDER BY source"
      ).fetchall()
      sources_recorded = sorted(r["source"] for r in rows)
      assert sources_recorded == ["chains", "local", "reddit", "slickdeals"]
      assert len(rows) == 4
      conn.close()
  ```

  > The `[sources.*]` URL keys above are the canonical ones each source reads: `reddit`/`slickdeals` use `listing_urls`, `chains` uses `offers_urls` (+ a `[sources.chains.branches]` map), `local` uses `feed_urls`. `user_agent` and `sources_enabled` live under `[meta]` (matching `load_config`'s mapping), and `[geocoder]` carries only `min_interval_seconds`/`max_live_calls`. The `FakeGeocoder` mapping in `_PatchedGeocoder` covers the `raw_location` strings the four recorded fixtures contain; a location not in the map resolves to `failed`, which is also a valid outcome (that deal simply falls to the list view).

- [ ] **Step 4 — Run the full-run test, expect PASS.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_run_main.py::test_full_offline_run_populates_db_and_scrape_runs -v
  ```

  Expected: PASS, 1 passed. (The test is fully offline — `httpx.get` and `Geocoder` are both monkeypatched. Do NOT make the test hit the live network or live Nominatim to make it pass.)

- [ ] **Step 5 — Run the whole `test_run_main.py` file** to confirm both tests pass together and nothing leaks network. Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest tests/test_run_main.py -v
  ```

  Expected: PASS, 2 passed.

- [ ] **Step 6 — Commit.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && git add tests/test_run_main.py && git commit -m "test(run): offline full-run over fixtures populates DB + scrape_runs per source"
  ```

  Expected: one commit created.

---

### Task 6.3: Write `TASK.md` — the MeshClaw run spec

Write the unattended-run instructions MeshClaw follows: run `python -m scrapers.run`, verify `scrape_runs` has a row per enabled source for this run, report per-source counts from the summary, flag any source that found 0 or errored, and exit non-zero only on total failure. Zero secrets.

**Files:** `TASK.md`

- [ ] **Step 1 — Create `/Users/jaehunb/projects/freemap/TASK.md`** with this exact content:

  ```markdown
  # TASK: FreeMap scheduled scrape (MeshClaw)

  Unattended scrape of all enabled sources into the SQLite DB. No secrets required
  (the geocoder is Nominatim — no API key). Run interactively first to confirm
  green, then on cron every 6–12h via `meshclaw run TASK.md`.

  ## What to do

  1. **Run the scrape** from the repo root:

     ```bash
     python -m scrapers.run
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
  python -c "import sqlite3, tomllib; \
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
    (`python -m scrapers.run` already returns `1` in that case; propagate it).
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
  - Do not point this at the web layer; the scraper and API share only the DB.
  ```

- [ ] **Step 2 — Sanity-check the verification snippet in `TASK.md` actually runs** against a freshly scraped DB by reusing the offline path manually (no live network). From the repo root, point at a temp DB seeded by the test flow is overkill here; instead just confirm the snippet parses and queries an existing schema. Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && python -c "import tomllib; cfg=tomllib.load(open('config.toml','rb')); print('db_path =', cfg['meta']['db_path'])"
  ```

  Expected: prints the configured `db_path` (confirms the `cfg['meta']['db_path']` access path used in the TASK.md snippet is correct for this `config.toml`). If your `config.toml` nests `db_path` under a different table, fix the snippet in `TASK.md` to match before committing.

- [ ] **Step 3 — Commit.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && git add TASK.md && git commit -m "docs(task): add MeshClaw run spec (run, verify scrape_runs, report, exit policy)"
  ```

  Expected: one commit created.

---

### Task 6.4: Write `README.md` — setup, run, serve, repoint metro, MeshClaw handoff

Document the full developer loop: venv, `pip install -r requirements.txt`, init DB, run scrapers, serve the API with uvicorn, how to repoint the metro via `config.toml`, and the MeshClaw handoff (`meshclaw run TASK.md` on cron, zero secrets).

**Files:** `README.md`

- [ ] **Step 1 — Confirm the API import path and the static mount** so the uvicorn command and the "open the app" instruction are accurate. Run:

  ```bash
  grep -n "FastAPI(\|StaticFiles\|app = \|mount(" /Users/jaehunb/projects/freemap/api/main.py
  ```

  Expected: shows `app = FastAPI(...)` and a `StaticFiles` mount serving `web/` at `/`. This confirms `uvicorn api.main:app` is correct and that the frontend is reachable at the server root.

- [ ] **Step 2 — Create `/Users/jaehunb/projects/freemap/README.md`** with this exact content:

  ```markdown
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
  ```

- [ ] **Step 3 — Verify every command in the README is real** (paths/flags exist). Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && \
    test -f requirements.txt && echo "requirements.txt OK" && \
    test -f config.toml && echo "config.toml OK" && \
    test -f db/schema.sql && echo "schema.sql OK" && \
    python -m scrapers.run --help >/dev/null 2>&1 && echo "run --help OK" && \
    python -c "import api.main; assert hasattr(api.main, 'app'); print('api.main:app OK')"
  ```

  Expected: prints `requirements.txt OK`, `config.toml OK`, `schema.sql OK`, `run --help OK`, `api.main:app OK`. If any line is missing, fix the README text to match reality (or the underlying file) before committing.

- [ ] **Step 4 — Commit.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && git add README.md && git commit -m "docs(readme): setup, scrape, serve, repoint metro, MeshClaw handoff"
  ```

  Expected: one commit created.

---

### Task 6.5: Final verification — no stubs remain, full suite green offline

Prove the milestone end state: no function is left as `NotImplementedError` (both Milestone 1 stubs were replaced in Milestone 2), and the entire test suite passes offline.

**Files:** none (verification only)

- [ ] **Step 1 — Assert no `NotImplementedError` stubs remain** anywhere in `scrapers/` or `api/`. Run:

  ```bash
  grep -rn "NotImplementedError" /Users/jaehunb/projects/freemap/scrapers /Users/jaehunb/projects/freemap/api || echo "NO STUBS REMAIN"
  ```

  Expected: `NO STUBS REMAIN`. If `run_pipeline` or `fetch_all_deals` still raise `NotImplementedError`, STOP — Milestone 2 was not completed; that is a blocker for the handoff (do not paper over it here).

- [ ] **Step 2 — Run the complete test suite offline** to confirm everything is green and nothing reaches the network. Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && python -m pytest -v
  ```

  Expected: PASS, all tests passed (every prior milestone's tests plus the two new `tests/test_run_main.py` tests). No test should hang on or attempt a live network/Nominatim call.

- [ ] **Step 3 — Confirm the handoff artifacts are present and tracked** by git. Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && git ls-files TASK.md README.md && echo "HANDOFF ARTIFACTS TRACKED"
  ```

  Expected: lists `README.md` and `TASK.md`, then `HANDOFF ARTIFACTS TRACKED`.

- [ ] **Step 4 — Tag the milestone (optional but recommended) and confirm clean tree.** Run:

  ```bash
  cd /Users/jaehunb/projects/freemap && git status --porcelain && git log --oneline -5
  ```

  Expected: `git status --porcelain` prints nothing (clean tree); `git log` shows the Milestone 6 commits (`feat(run): add main()`, `test(run): offline full-run`, `docs(task)`, `docs(readme)`). End state: a single unattended, offline-testable entrypoint (`python -m scrapers.run`) ready for `meshclaw run TASK.md`, fully documented.