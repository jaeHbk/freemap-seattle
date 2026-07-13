// Shared types + pure helpers for the FreeMap UI. The API lane owns the route
// handlers; this file only encodes the documented response shape and the
// presentation-side partition/guard logic ported 1:1 from the old web/*.js.

export type DealType = "free" | "bogo" | "other";
export type Category = "food" | "retail" | "event" | "other";
export type Placement = "physical" | "online";
export type DealStatus = "active" | "stale" | "expired";
export type GeocodeStatus = "ok" | "failed" | "n/a" | "pending";

export interface Deal {
  id: number | string;
  source: string;
  source_id: string;
  dedup_key: string;
  title: string;
  url: string;
  description: string | null;
  deal_type: DealType;
  category: Category;
  placement: Placement;
  lat: number | null;
  lng: number | null;
  raw_location: string | null;
  geocode_status: GeocodeStatus;
  posted_at: string | null;
  expires_at: string | null;
  first_seen: string | null;
  last_seen: string | null;
  status: DealStatus;
  alt_urls?: string[];
}

export interface FilterState {
  type: "" | DealType;
  category: "" | Category;
  placement: "" | Placement;
  includeStale: boolean;
}

export const EMPTY_FILTERS: FilterState = {
  type: "",
  category: "",
  placement: "",
  includeStale: false,
};

export const SEATTLE: [number, number] = [47.6062, -122.3321];
export const SEATTLE_ZOOM = 12;

// safeHttpUrl(u) -> u if it is an http(s) URL, else null. Deal data is scraped
// from UNTRUSTED sources, so we never emit javascript:/data:/etc. as an href.
// Ported verbatim from web/map.js.
export function safeHttpUrl(u: unknown): string | null {
  if (typeof u !== "string") return null;
  const t = u.trim();
  return /^https?:\/\//i.test(t) ? t : null;
}

// buildQuery(state) -> querystring (no leading "?") for GET /api/deals.
// Only truthy filter fields are emitted. NOTE: no bbox — the API excludes
// coordless deals when a bbox is present, so the map is scoped client-side.
// Ported from web/filters.js.
export function buildQuery(state: FilterState): string {
  const p = new URLSearchParams();
  if (state.type) p.set("type", state.type);
  if (state.category) p.set("category", state.category);
  if (state.placement) p.set("placement", state.placement);
  if (state.includeStale) p.set("include_stale", "true");
  return p.toString();
}

// matchesFilters(deal, state) -> client-side guard mirroring server filters so a
// deal already in memory can be re-checked without a refetch. Ported from
// web/filters.js. include_stale is the server's source of truth; this only
// refilters the in-memory set so toggling placement/type doesn't refetch.
export function matchesFilters(deal: Deal, state: FilterState): boolean {
  if (deal.status === "expired") return false;
  if (deal.status === "stale" && !state.includeStale) return false;
  if (state.type && deal.deal_type !== state.type) return false;
  if (state.category && deal.category !== state.category) return false;
  if (state.placement && deal.placement !== state.placement) return false;
  return true;
}

// belongsInList(deal) -> a deal belongs in the list view if it is online, OR a
// physical deal we could not geocode (so it is never lost). Ported from web/list.js.
export function belongsInList(deal: Deal): boolean {
  return deal.placement === "online" || deal.geocode_status === "failed";
}

// hasCoords — a deal that can be plotted: physical + real lat/lng.
export function hasCoords(deal: Deal): deal is Deal & { lat: number; lng: number } {
  return deal.placement === "physical" && deal.lat != null && deal.lng != null;
}

// dealsForMap(deals, state) -> geocoded physical deals that pass active filters.
// Viewport scoping is left to leaflet's clusterer (it culls offscreen markers),
// which keeps this pure and avoids a refetch on every pan. Ported from web/map.js
// (the inViewport step is now handled by the map itself).
export function dealsForMap(deals: Deal[], state: FilterState): Deal[] {
  return deals.filter((d) => hasCoords(d) && matchesFilters(d, state));
}

// dealsForList(deals, state) -> online + failed-geocode deals passing filters.
export function dealsForList(deals: Deal[], state: FilterState): Deal[] {
  return deals.filter((d) => belongsInList(d) && matchesFilters(d, state));
}
