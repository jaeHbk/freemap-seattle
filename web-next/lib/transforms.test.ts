// Run: node --test --experimental-strip-types lib/transforms.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  computeStatus,
  naiveLocalIso,
  parseBbox,
  inBbox,
  collapseDedup,
  BboxError,
} from "./transforms.ts";
import type { Deal } from "./db.ts";

// Minimal Deal factory so test fixtures stay terse but type-check.
function mk(p: Partial<Deal>): Deal {
  return {
    id: 1, source: "s", source_id: "x", dedup_key: null, title: "t", url: "u",
    description: null, eligibility: null, redemption: null, verified_at: null,
    deal_type: "free", category: "food", placement: "online",
    lat: null, lng: null, raw_location: null, geocode_status: "n/a",
    posted_at: null, expires_at: null, first_seen: null, last_seen: null,
    alt_urls: [], ...p,
  };
}

// --- parseBbox / inBbox -----------------------------------------------------
test("parseBbox", () => {
  assert.equal(parseBbox(null), null);
  assert.equal(parseBbox(""), null);
  assert.deepEqual(parseBbox("-122.45,47.50,-122.20,47.75"), [-122.45, 47.5, -122.2, 47.75]);
  // wrong arity -> error
  assert.throws(() => parseBbox("1,2,3"), BboxError);
  assert.throws(() => parseBbox("1,2,3,4,5"), BboxError);
  // non-finite -> error (nan/inf must 400, not silently pass)
  assert.throws(() => parseBbox("nan,2,3,4"), BboxError);
  assert.throws(() => parseBbox("inf,2,3,4"), BboxError);
  assert.throws(() => parseBbox("a,b,c,d"), BboxError);
});

test("inBbox", () => {
  const bbox = parseBbox("-122.45,47.50,-122.20,47.75")!;
  assert.equal(inBbox({ lat: 47.62, lng: -122.32 }, bbox), true); // inside
  assert.equal(inBbox({ lat: 47.62, lng: -121.0 }, bbox), false); // outside
  assert.equal(inBbox({ lat: null, lng: null }, bbox), false); // coordless excluded
  assert.equal(inBbox({ lat: 47.5, lng: -122.45 }, bbox), true); // inclusive lower corner
  assert.equal(inBbox({ lat: 47.75, lng: -122.2 }, bbox), true); // inclusive upper corner
  assert.equal(inBbox({ lat: 99, lng: 99 }, null), true); // null bbox accepts all
});

// --- computeStatus freshness transitions (from pipeline.compute_status) ---
test("computeStatus transitions", () => {
  const now = "2026-06-26T12:00:00";
  // expired: expires_at in the past
  assert.equal(computeStatus("2026-06-25T12:00:00", now, now), "expired");
  // future expiry + fresh last_seen -> active
  assert.equal(computeStatus("2026-06-27T12:00:00", "2026-06-26T11:00:00", now), "active");
  // future expiry but old last_seen -> stale (expiry check doesn't suppress stale; 1:1 with Python)
  assert.equal(computeStatus("2026-06-27T12:00:00", "2026-06-01T00:00:00", now), "stale");
  // stale: last_seen > 24h before now, no expiry
  assert.equal(computeStatus(null, "2026-06-25T11:00:00", now), "stale");
  // active: last_seen within 24h
  assert.equal(computeStatus(null, "2026-06-26T00:00:00", now), "active");
  // boundary: exactly 24h ago is NOT stale (strictly greater than)
  assert.equal(computeStatus(null, "2026-06-25T12:00:00", now), "active");
  // just over 24h is stale
  assert.equal(computeStatus(null, "2026-06-25T11:59:59", now), "stale");
  // no dates -> active
  assert.equal(computeStatus(null, null, now), "active");
  // custom staleAfterHours
  assert.equal(computeStatus(null, "2026-06-26T10:00:00", now, 1), "stale"); // 2h > 1h
  assert.equal(computeStatus(null, "2026-06-26T11:30:00", now, 1), "active"); // 0.5h <= 1h
});

test("computeStatus mixed aware/naive never throws (naive read as UTC)", () => {
  // Aware now (offset) vs naive last_seen: must not throw, must compare in UTC.
  // now = 12:00Z; last_seen 11:00 naive -> read as 11:00Z -> 1h ago -> active.
  assert.equal(computeStatus(null, "2026-06-26T11:00:00", "2026-06-26T05:00:00-07:00"), "active");
  // expires_at aware in the past relative to aware now
  assert.equal(
    computeStatus("2026-06-26T04:00:00-07:00", null, "2026-06-26T05:00:00-07:00"),
    "expired",
  );
  // Date object now also accepted.
  assert.equal(computeStatus(null, null, new Date("2026-06-26T12:00:00Z")), "active");
});

// --- collapseDedup / alt_urls ----------------------------------------------
test("naiveLocalIso + computeStatus: now and last_seen compared as naive (no host-TZ skew)", () => {
  // The scraper writes naive-LOCAL timestamps; the route must pass a naive-local
  // `now` (via naiveLocalIso), NOT a Date. With stale_after_hours=24, a deal seen
  // ~17h ago in local wall-clock must read 'active'. Passing a Date here would
  // mislabel last_seen as UTC and skew the boundary by the host offset, wrongly
  // flipping it to 'stale'. This locks the fix the adversarial gate caught.
  const now = new Date("2026-06-26T14:00:00"); // local wall-clock
  const nowIso = naiveLocalIso(now);
  // naiveLocalIso must echo local components, not a UTC-shifted string.
  assert.equal(nowIso, "2026-06-26T14:00:00");
  const seen17hAgo = "2026-06-25T21:00:00"; // 17h before, naive local
  assert.equal(computeStatus(null, seen17hAgo, nowIso), "active");
  // And a 25h-old deal is stale regardless of host TZ.
  assert.equal(computeStatus(null, "2026-06-25T13:00:00", nowIso), "stale");
});

test("collapseDedup collapses groups into primary.alt_urls", () => {
  const a = mk({ id: 1, dedup_key: "k", url: "url-a" });
  const b = mk({ id: 2, dedup_key: "k", url: "url-b" });
  const c = mk({ id: 3, dedup_key: "k", url: "url-c" });
  const result = collapseDedup([a, b, c]);
  assert.equal(result.length, 1);
  assert.equal(result[0], a); // first-seen wins
  assert.deepEqual(result[0].alt_urls, ["url-b", "url-c"]);
});

test("collapseDedup skips duplicate and self urls", () => {
  const a = mk({ id: 1, dedup_key: "k", url: "same" });
  const b = mk({ id: 2, dedup_key: "k", url: "same" }); // self == primary url
  const c = mk({ id: 3, dedup_key: "k", url: "other" });
  const d = mk({ id: 4, dedup_key: "k", url: "other" }); // dupe of c's contributed url
  const result = collapseDedup([a, b, c, d]);
  assert.equal(result.length, 1);
  assert.deepEqual(result[0].alt_urls, ["other"]);
});

test("collapseDedup leaves falsy-key rows standalone", () => {
  const a = mk({ id: 1, dedup_key: null, url: "a" });
  const b = mk({ id: 2, dedup_key: "", url: "b" });
  const c = mk({ id: 3, dedup_key: "k", url: "c" });
  const result = collapseDedup([a, b, c]);
  assert.equal(result.length, 3);
  assert.deepEqual(result.map((d) => d.id), [1, 2, 3]);
});
