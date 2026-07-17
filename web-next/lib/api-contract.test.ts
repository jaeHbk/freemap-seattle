import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSourceMetadata,
  parseDealId,
  parseIncludeStale,
  selectDeals,
} from "./api-contract.ts";
import type { Deal } from "./db.ts";

const NOW = "2026-07-16T12:00:00";

function deal(overrides: Partial<Deal> = {}): Deal {
  return {
    id: 1,
    source: "places_brand",
    source_id: "deal-1",
    dedup_key: "one",
    title: "Free coffee",
    url: "https://example.com/one",
    description: null,
    eligibility: null,
    redemption: null,
    verified_at: null,
    deal_type: "free",
    category: "food",
    placement: "physical",
    lat: 47.62,
    lng: -122.32,
    raw_location: "Seattle",
    geocode_status: "ok",
    posted_at: null,
    expires_at: "2026-08-01T00:00:00",
    first_seen: "2026-07-16T10:00:00",
    last_seen: "2026-07-16T11:00:00",
    alt_urls: [],
    ...overrides,
  };
}

const ALL_FILTERS = {
  type: null,
  category: null,
  placement: null,
  includeStale: false,
};

test("parseIncludeStale preserves accepted query coercions", () => {
  for (const value of ["true", "True", "1", "yes", "on"]) {
    assert.equal(parseIncludeStale(value), true);
  }
  for (const value of [null, "", "false", "0", "no"]) {
    assert.equal(parseIncludeStale(value), false);
  }
});

test("parseDealId accepts safe integers and rejects malformed IDs", () => {
  assert.equal(parseDealId("42"), 42);
  assert.equal(parseDealId("-1"), -1);
  assert.equal(parseDealId("1.5"), null);
  assert.equal(parseDealId("abc"), null);
  assert.equal(parseDealId("9007199254740992"), null);
});

test("selectDeals enforces freshness, filters, and deduplication", () => {
  const rows = [
    deal(),
    deal({
      id: 2,
      source_id: "deal-2",
      url: "https://example.com/two",
    }),
    deal({
      id: 3,
      source_id: "deal-3",
      dedup_key: "stale",
      title: "Stale coffee",
      last_seen: "2026-07-14T00:00:00",
    }),
    deal({
      id: 4,
      source_id: "deal-4",
      dedup_key: "expired",
      expires_at: "2026-07-01T00:00:00",
    }),
    deal({
      id: 5,
      source_id: "deal-5",
      dedup_key: null,
      deal_type: "bogo",
      category: "retail",
      placement: "online",
    }),
  ];

  const active = selectDeals(rows, ALL_FILTERS, NOW);
  assert.deepEqual(active.map((row) => row.id), [1, 5]);
  assert.deepEqual(active[0]?.alt_urls, ["https://example.com/two"]);
  assert.equal(active[0]?.status, "active");

  const stale = selectDeals(
    rows,
    { ...ALL_FILTERS, includeStale: true },
    NOW,
  );
  assert.deepEqual(stale.map((row) => row.id), [1, 3, 5]);
  assert.equal(stale[1]?.status, "stale");

  const filtered = selectDeals(
    rows,
    {
      type: "bogo",
      category: "retail",
      placement: "online",
      includeStale: false,
    },
    NOW,
  );
  assert.deepEqual(filtered.map((row) => row.id), [5]);
});

test("selectDeals handles aware expiry timestamps without throwing", () => {
  const rows = [
    deal({ expires_at: "2026-07-16T23:59:00-07:00" }),
  ];
  assert.deepEqual(
    selectDeals(rows, ALL_FILTERS, NOW).map((row) => row.id),
    [1],
  );
});

test("buildSourceMetadata unions sources and includes latest telemetry", () => {
  const result = buildSourceMetadata(
    [
      { source: "places_brand", n: 40 },
      { source: "reddit", n: 2 },
    ],
    [{ source: "places_brand", last_ok: "2026-07-16T12:00:00" }],
    [
      {
        source: "places_brand",
        finished_at: "2026-07-16T12:00:00",
        deals_found: 40,
        deals_upserted: 40,
        map_pins: 38,
        geocode_failures: 2,
        duration_ms: 500,
        errors: null,
      },
      {
        source: "reddit",
        finished_at: "2026-07-16T12:00:01",
        deals_found: 0,
        errors: "rate limited",
      },
    ],
  );

  assert.deepEqual(result.sources, [
    {
      source: "places_brand",
      deal_count: 40,
      last_successful_scrape: "2026-07-16T12:00:00",
      latest_run: {
        finished_at: "2026-07-16T12:00:00",
        status: "ok",
        deals_found: 40,
        deals_upserted: 40,
        map_pins: 38,
        geocode_failures: 2,
        duration_ms: 500,
      },
    },
    {
      source: "reddit",
      deal_count: 2,
      last_successful_scrape: null,
      latest_run: {
        finished_at: "2026-07-16T12:00:01",
        status: "error",
        deals_found: 0,
        deals_upserted: null,
        map_pins: null,
        geocode_failures: null,
        duration_ms: null,
      },
    },
  ]);
});
