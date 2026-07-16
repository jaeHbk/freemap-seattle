import assert from "node:assert/strict";
import test from "node:test";

import {
  dealsToFeatureCollection,
  OPENFREEMAP_STYLE_URL,
} from "./deal-map-data.ts";
import type { Deal } from "./deals.ts";

function deal(overrides: Partial<Deal> = {}): Deal {
  return {
    id: 7,
    source: "places_brand",
    source_id: "store-7",
    dedup_key: null,
    title: "Free lunch",
    url: "https://example.com/deal",
    description: null,
    deal_type: "free",
    category: "food",
    placement: "physical",
    lat: 47.61,
    lng: -122.33,
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

test("OpenFreeMap style is keyless HTTPS", () => {
  const url = new URL(OPENFREEMAP_STYLE_URL);
  assert.equal(url.protocol, "https:");
  assert.equal(url.hostname, "tiles.openfreemap.org");
  assert.equal(url.search, "");
});

test("dealsToFeatureCollection creates MapLibre point features", () => {
  assert.deepEqual(dealsToFeatureCollection([deal()]), {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "7",
        geometry: {
          type: "Point",
          coordinates: [-122.33, 47.61],
        },
        properties: {
          dealId: "7",
          dealType: "free",
          status: "active",
          title: "Free lunch",
        },
      },
    ],
  });
});

test("dealsToFeatureCollection omits rows without coordinates", () => {
  const rows = [
    deal({ id: 1, lat: null }),
    deal({ id: 2, lng: null }),
    deal({ id: 3, deal_type: "bogo", status: "stale" }),
  ];

  const result = dealsToFeatureCollection(rows);
  assert.equal(result.features.length, 1);
  assert.deepEqual(result.features[0]?.properties, {
    dealId: "3",
    dealType: "bogo",
    status: "stale",
    title: "Free lunch",
  });
});
