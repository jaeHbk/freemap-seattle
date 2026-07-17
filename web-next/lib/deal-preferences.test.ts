import assert from "node:assert/strict";
import test from "node:test";

import type { Deal } from "../components/deals.ts";
import {
  DEFAULT_ALERT_PREFERENCES,
  dealPreferenceKey,
  mergeSeenDealKeys,
  parseAlertPreferences,
  parseFavoriteKeys,
  serializeFavoriteKeys,
  unseenNearbyDeals,
} from "./deal-preferences.ts";

function deal(
  id: number,
  overrides: Partial<Deal> = {},
): Deal {
  return {
    id,
    source: "places_brand",
    source_id: `store-${id}`,
    dedup_key: null,
    title: `Deal ${id}`,
    url: "https://example.com",
    description: null,
    deal_type: "free",
    category: "food",
    placement: "physical",
    lat: 47.6062,
    lng: -122.3321,
    raw_location: "Seattle",
    geocode_status: "ok",
    posted_at: null,
    expires_at: null,
    first_seen: null,
    last_seen: null,
    status: "active",
    ...overrides,
  };
}

test("favorite keys are stable across database id changes", () => {
  assert.equal(
    dealPreferenceKey(deal(1)),
    dealPreferenceKey(deal(999, { source_id: "store-1" })),
  );
});

test("favorite storage parsing is defensive and deterministic", () => {
  assert.deepEqual(
    [...parseFavoriteKeys('["b","a","a",12]')],
    ["b", "a"],
  );
  assert.deepEqual([...parseFavoriteKeys("not-json")], []);
  assert.equal(serializeFavoriteKeys(new Set(["b", "a"])), '["a","b"]');
});

test("alert preferences clamp radius and deduplicate seen keys", () => {
  assert.deepEqual(parseAlertPreferences(null), DEFAULT_ALERT_PREFERENCES);
  assert.deepEqual(
    parseAlertPreferences(
      JSON.stringify({
        enabled: true,
        radiusMiles: 99,
        seenDealKeys: ["a", "a", "b"],
      }),
    ),
    { enabled: true, radiusMiles: 10, seenDealKeys: ["a", "b"] },
  );
});

test("unseenNearbyDeals requires active, unseen, mapped deals in radius", () => {
  const origin = {
    lat: 47.6062,
    lng: -122.3321,
    label: "Downtown",
    source: "search" as const,
  };
  const nearby = deal(1);
  const seen = deal(2);
  const far = deal(3, { lat: 47.75, lng: -122.2 });
  const online = deal(4, {
    placement: "online",
    lat: null,
    lng: null,
    geocode_status: "n/a",
  });
  const stale = deal(5, { status: "stale" });

  assert.deepEqual(
    unseenNearbyDeals(
      [nearby, seen, far, online, stale],
      [dealPreferenceKey(seen)],
      origin,
      3,
    ).map((candidate) => candidate.id),
    [1],
  );
  assert.deepEqual(
    unseenNearbyDeals([nearby], [], null, 3),
    [],
  );
});

test("mergeSeenDealKeys retains a bounded deduplicated snapshot", () => {
  assert.deepEqual(
    mergeSeenDealKeys(
      [dealPreferenceKey(deal(1))],
      [deal(1), deal(2)],
    ),
    [
      dealPreferenceKey(deal(1)),
      dealPreferenceKey(deal(2)),
    ],
  );
});
