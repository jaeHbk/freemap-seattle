// Pure, dependency-free filter helpers. Exposed on window for the browser AND
// exported via module.exports for Node-run unit tests (no build step either way).

// buildQuery(state) -> querystring (no leading "?") for GET /api/deals.
// state shape: { type, category, placement, bbox, includeStale }
// Only truthy filter fields are emitted. bbox is "minLng,minLat,maxLng,maxLat".
function buildQuery(state) {
  state = state || {};
  const params = [];
  if (state.type) params.push("type=" + encodeURIComponent(state.type));
  if (state.category) params.push("category=" + encodeURIComponent(state.category));
  if (state.placement) params.push("placement=" + encodeURIComponent(state.placement));
  if (state.bbox) params.push("bbox=" + encodeURIComponent(state.bbox));
  if (state.includeStale) params.push("include_stale=true");
  return params.join("&");
}

// matchesFilters added in the next task.

if (typeof module !== "undefined" && module.exports) {
  module.exports = { buildQuery };
}
if (typeof window !== "undefined") {
  window.buildQuery = buildQuery;
}
