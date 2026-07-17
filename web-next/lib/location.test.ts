import { test } from "node:test";
import assert from "node:assert/strict";

import type { Deal } from "../components/deals.ts";
import {
  distanceMiles,
  isInSeattleArea,
  parseCensusLocation,
  resolveNeighborhood,
  sortDealsByDistance,
  type SearchOrigin,
} from "./location.ts";

function deal(id: number, lat: number | null, lng: number | null): Deal {
  return {
    id,
    source: "test",
    source_id: String(id),
    dedup_key: null,
    title: `Deal ${id}`,
    url: "https://example.com",
    description: null,
    deal_type: "free",
    category: "food",
    placement: lat == null ? "online" : "physical",
    lat,
    lng,
    raw_location: null,
    geocode_status: lat == null ? "n/a" : "ok",
    posted_at: null,
    expires_at: null,
    first_seen: null,
    last_seen: null,
    status: "active",
  };
}

test("resolveNeighborhood accepts names, aliases, and Seattle suffixes", () => {
  assert.equal(resolveNeighborhood("Ballard")?.label, "Ballard");
  assert.equal(resolveNeighborhood("SLU, Seattle WA")?.label, "South Lake Union");
  assert.equal(resolveNeighborhood("unknown"), null);
});

test("distanceMiles computes a stable Seattle-scale distance", () => {
  const miles = distanceMiles(
    { lat: 47.6062, lng: -122.3321 },
    { lat: 47.6687, lng: -122.386 },
  );
  assert.ok(miles > 4.5 && miles < 5.5);
});

test("sortDealsByDistance places mapped nearest deals first", () => {
  const origin: SearchOrigin = {
    lat: 47.6062,
    lng: -122.3321,
    label: "Downtown",
    source: "search",
  };
  const far = deal(1, 47.7, -122.4);
  const online = deal(2, null, null);
  const near = deal(3, 47.607, -122.333);

  assert.deepEqual(sortDealsByDistance([far, online, near], origin), [
    near,
    far,
    online,
  ]);
});

test("isInSeattleArea gates coordinates on every bound", () => {
  // Inside, and on each inclusive edge.
  assert.equal(isInSeattleArea(47.6062, -122.3321), true);
  assert.equal(isInSeattleArea(47.45, -122.46), true);
  assert.equal(isInSeattleArea(47.75, -122.2), true);
  // Just past each bound, and clearly remote (Portland) — the "Near me" gap.
  assert.equal(isInSeattleArea(47.44, -122.3), false);
  assert.equal(isInSeattleArea(47.76, -122.3), false);
  assert.equal(isInSeattleArea(47.6, -122.47), false);
  assert.equal(isInSeattleArea(47.6, -122.19), false);
  assert.equal(isInSeattleArea(45.5231, -122.6765), false);
});

test("parseCensusLocation accepts Seattle matches and rejects remote matches", () => {
  assert.deepEqual(
    parseCensusLocation({
      result: {
        addressMatches: [
          {
            matchedAddress: "400 BROAD ST, SEATTLE, WA, 98109",
            coordinates: { x: -122.3493, y: 47.6205 },
          },
        ],
      },
    }),
    {
      lat: 47.6205,
      lng: -122.3493,
      label: "400 BROAD ST, SEATTLE, WA, 98109",
      source: "search",
    },
  );
  assert.equal(
    parseCensusLocation({
      result: {
        addressMatches: [
          {
            matchedAddress: "PORTLAND, OR",
            coordinates: { x: -122.6765, y: 45.5231 },
          },
        ],
      },
    }),
    null,
  );
});
