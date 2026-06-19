// Node-run unit tests for web/filters.js. Run: node web/filters.test.js
const assert = require("assert");
const { buildQuery, matchesFilters } = require("./filters.js");

// --- buildQuery ---
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

// --- matchesFilters ---
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

console.log("filters.test.js OK");
