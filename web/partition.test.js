// Node-run unit tests for the map-vs-list partition in web/map.js.
// Run: node web/partition.test.js
//
// Spec: MAP shows geocoded physical deals that fall inside the current viewport;
// LIST shows online deals + failed-geocode physical deals (belongsInList). A deal
// belongs to exactly one of the two sets — never both.
const assert = require("assert");
const { dealsForMap, dealsForList, inViewport } = require("./map.js");

// A tiny stand-in for Leaflet's LatLngBounds: contains([lat, lng]) -> bool.
// Viewport = Seattle-ish box.
const bounds = {
  contains([lat, lng]) {
    return lat >= 47.5 && lat <= 47.75 && lng >= -122.45 && lng <= -122.2;
  },
};

const physInView = {
  placement: "physical", geocode_status: "ok", status: "active",
  deal_type: "free", category: "food", lat: 47.62, lng: -122.32,
};
const physOutOfView = {
  placement: "physical", geocode_status: "ok", status: "active",
  deal_type: "free", category: "food", lat: 47.60, lng: -121.00, // Bellevue
};
const online = {
  placement: "online", geocode_status: "n/a", status: "active",
  deal_type: "free", category: "food", lat: null, lng: null,
};
const failedGeo = {
  placement: "physical", geocode_status: "failed", status: "active",
  deal_type: "free", category: "food", lat: null, lng: null,
};

const all = [physInView, physOutOfView, online, failedGeo];
const noFilter = {};

// inViewport guards null coords and uses bounds.contains.
assert.strictEqual(inViewport(physInView, bounds), true);
assert.strictEqual(inViewport(physOutOfView, bounds), false);
assert.strictEqual(inViewport(online, bounds), false); // null coords
assert.strictEqual(inViewport(failedGeo, bounds), false); // null coords

// MAP set = geocoded physical deals inside the viewport ONLY.
const mapSet = dealsForMap(all, bounds, noFilter);
assert.deepStrictEqual(mapSet, [physInView]);

// LIST set = online + failed-geocode physical (belongsInList), regardless of bbox.
const listSet = dealsForList(all, noFilter);
assert.deepStrictEqual(listSet, [online, failedGeo]);

// No deal appears in both sets.
for (const d of mapSet) assert.ok(!listSet.includes(d), "deal in both map and list");

// Filters still apply to both partitions.
const onlyBogo = { type: "bogo" };
assert.deepStrictEqual(dealsForMap(all, bounds, onlyBogo), []);
assert.deepStrictEqual(dealsForList(all, onlyBogo), []);

console.log("partition.test.js OK");
