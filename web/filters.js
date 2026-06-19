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

// matchesFilters(deal, state) -> bool. Client-side guard mirroring server filters
// so a deal already in memory can be re-checked without a refetch. includeStale
// gates stale deals; expired deals never match (server already excludes them, but
// we defend here too).
function matchesFilters(deal, state) {
  state = state || {};
  if (deal.status === "expired") return false;
  if (deal.status === "stale" && !state.includeStale) return false;
  if (state.type && deal.deal_type !== state.type) return false;
  if (state.category && deal.category !== state.category) return false;
  if (state.placement && deal.placement !== state.placement) return false;
  return true;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { buildQuery, matchesFilters };
}
if (typeof window !== "undefined") {
  window.buildQuery = buildQuery;
  window.matchesFilters = matchesFilters;
}
