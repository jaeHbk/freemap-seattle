// Run: node --test --experimental-strip-types components/deals.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildQuery,
  dealsForList,
  dealsForMap,
  matchesFilters,
  safeHttpUrl,
  type Deal,
} from "./deals.ts";

function mk(p: Partial<Deal> = {}): Deal {
  return {
    id: 1,
    source: "source",
    source_id: "id",
    dedup_key: null,
    title: "Free coffee",
    url: "https://example.com/deal",
    description: null,
    deal_type: "free",
    category: "food",
    placement: "online",
    lat: null,
    lng: null,
    raw_location: null,
    geocode_status: "n/a",
    posted_at: null,
    expires_at: null,
    first_seen: null,
    last_seen: null,
    status: "active",
    alt_urls: [],
    ...p,
  };
}

test("safeHttpUrl accepts only HTTP(S)", () => {
  assert.equal(safeHttpUrl(" https://example.com "), "https://example.com");
  assert.equal(safeHttpUrl("http://example.com"), "http://example.com");
  assert.equal(safeHttpUrl("javascript:alert(1)"), null);
  assert.equal(safeHttpUrl(null), null);
});

test("buildQuery emits the filters used by the app", () => {
  assert.equal(buildQuery({ type: "", category: "", placement: "", includeStale: false }), "");
  assert.equal(
    buildQuery({ type: "bogo", category: "food", placement: "physical", includeStale: true }),
    "type=bogo&category=food&placement=physical&include_stale=true",
  );
});

test("matchesFilters enforces status and selected values", () => {
  const active = mk({ placement: "physical" });
  assert.equal(
    matchesFilters(active, { type: "free", category: "food", placement: "physical", includeStale: false }),
    true,
  );
  assert.equal(
    matchesFilters(active, { type: "bogo", category: "", placement: "", includeStale: false }),
    false,
  );
  assert.equal(
    matchesFilters(mk({ status: "stale" }), { type: "", category: "", placement: "", includeStale: false }),
    false,
  );
  assert.equal(
    matchesFilters(mk({ status: "stale" }), { type: "", category: "", placement: "", includeStale: true }),
    true,
  );
  assert.equal(
    matchesFilters(mk({ status: "expired" }), { type: "", category: "", placement: "", includeStale: true }),
    false,
  );
});

test("map shows plottable deals while list shows every matching deal", () => {
  const seattlePin = mk({ id: 1, placement: "physical", geocode_status: "ok", lat: 47.62, lng: -122.32 });
  const offscreenPin = mk({ id: 2, placement: "physical", geocode_status: "ok", lat: 47.6, lng: -121 });
  const online = mk({ id: 3 });
  const failedGeo = mk({ id: 4, placement: "physical", geocode_status: "failed" });
  const all = [seattlePin, offscreenPin, online, failedGeo];
  const filters = { type: "", category: "", placement: "", includeStale: false } as const;

  // The app fetches its small map payload once. MapLibre clusters and culls
  // offscreen markers, while /api/deals?bbox= remains available for bounded clients.
  assert.deepEqual(dealsForMap(all, filters), [seattlePin, offscreenPin]);
  assert.deepEqual(dealsForList(all, filters), all);
});

test("list applies the same active filters as the map", () => {
  const freePhysical = mk({
    id: 1,
    placement: "physical",
    geocode_status: "ok",
    lat: 47.62,
    lng: -122.32,
  });
  const bogoOnline = mk({ id: 2, deal_type: "bogo" });
  const staleFree = mk({ id: 3, status: "stale" });
  const filters = {
    type: "free",
    category: "",
    placement: "",
    includeStale: false,
  } as const;

  assert.deepEqual(
    dealsForList([freePhysical, bogoOnline, staleFree], filters),
    [freePhysical],
  );
});
