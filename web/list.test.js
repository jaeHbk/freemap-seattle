// Node-run unit tests for web/list.js. Run: node web/list.test.js
const assert = require("assert");
const { belongsInList } = require("./list.js");

assert.strictEqual(belongsInList({ placement: "online", geocode_status: "n/a" }), true);
assert.strictEqual(belongsInList({ placement: "physical", geocode_status: "failed" }), true);
assert.strictEqual(belongsInList({ placement: "physical", geocode_status: "ok" }), false);

console.log("list.test.js OK");
