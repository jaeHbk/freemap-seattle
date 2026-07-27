import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_URL_STATE,
  parseUrlState,
  serializeUrlState,
  type AppUrlState,
} from "./url-state.ts";

test("parseUrlState returns defaults for an empty query", () => {
  assert.deepEqual(parseUrlState(new URLSearchParams()), DEFAULT_URL_STATE);
});

test("URL state round trips every shareable application field", () => {
  const state: AppUrlState = {
    market: "atlanta",
    view: "list",
    filters: {
      type: "bogo",
      category: "food",
      placement: "physical",
      includeStale: true,
    },
    origin: {
      lat: 33.764123,
      lng: -84.371321,
      label: "Old Fourth Ward",
      source: "geolocation",
    },
    selectedDealId: "deal:42",
    detailsOpen: true,
    mapViewport: { lat: 33.764, lng: -84.371, zoom: 14.375 },
  };

  const serialized = serializeUrlState(state);
  assert.deepEqual(parseUrlState(serialized), {
    ...state,
    origin: { ...state.origin, lat: 33.76412, lng: -84.37132 },
    mapViewport: { lat: 33.764, lng: -84.371, zoom: 14.38 },
  });
});

test("parseUrlState ignores malformed and out-of-range values", () => {
  const parsed = parseUrlState(
    new URLSearchParams({
      view: "grid",
      market: "chicago",
      type: "coupon",
      category: "travel",
      placement: "mail",
      stale: "true",
      origin: "999,-999",
      origin_label: "Somewhere",
      deal: "<script>",
      details: "1",
      map: "47.6,-122.3,99",
    }),
  );

  assert.deepEqual(parsed, DEFAULT_URL_STATE);
});

test("serializeUrlState preserves unrelated query parameters", () => {
  const params = serializeUrlState(
    {
      ...DEFAULT_URL_STATE,
      view: "list",
      filters: { ...DEFAULT_URL_STATE.filters, type: "free" },
    },
    new URLSearchParams("utm_source=newsletter&view=map&type=bogo"),
  );

  assert.equal(
    params.toString(),
    "utm_source=newsletter&view=list&type=free",
  );
});
