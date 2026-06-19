// Node-run unit tests for web/map.js safeHttpUrl (XSS allowlist).
// Run: node web/map.test.js
const assert = require("assert");
const { safeHttpUrl } = require("./map.js");

// http(s) URLs pass through (trimmed).
assert.strictEqual(safeHttpUrl("https://example.com/x"), "https://example.com/x");
assert.strictEqual(safeHttpUrl("http://example.com/x"), "http://example.com/x");
assert.strictEqual(safeHttpUrl("  https://example.com/x  "), "https://example.com/x");

// Dangerous schemes are rejected (returns null -> rendered as plain text, no href).
assert.strictEqual(safeHttpUrl("javascript:alert(1)"), null);
assert.strictEqual(safeHttpUrl("JavaScript:alert(1)"), null);
assert.strictEqual(safeHttpUrl("data:text/html,<script>alert(1)</script>"), null);
assert.strictEqual(safeHttpUrl("vbscript:msgbox(1)"), null);
assert.strictEqual(safeHttpUrl(""), null);
assert.strictEqual(safeHttpUrl(undefined), null);
assert.strictEqual(safeHttpUrl(null), null);
assert.strictEqual(safeHttpUrl(123), null);

console.log("map.test.js OK");
