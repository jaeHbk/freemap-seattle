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
    eligibility     TEXT,
    redemption      TEXT,
    verified_at     TIMESTAMP,
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

-- Spatial path: the map query filters lat/lng to a bbox (fetch_deals_in_bbox).
CREATE INDEX IF NOT EXISTS idx_deals_lat_lng ON deals(lat, lng);

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
    deals_upserted  INTEGER,
    map_pins        INTEGER,
    geocode_failures INTEGER,
    duration_ms     INTEGER,
    errors          TEXT
);
