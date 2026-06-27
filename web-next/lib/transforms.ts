// Pure transform helpers — 1:1 ports of the Python read API (api/main.py +
// scrapers/pipeline.py) and the node-tested JS helpers (web/filters.js, list.js,
// map.js). No DB, no I/O, no framework. Every function here is total.

import type { Deal } from "./db";

// --- Filter state shape (mirrors web/map.js filterState / buildQuery input) ---
export type FilterState = {
  type?: string;
  category?: string;
  placement?: string;
  bbox?: string;
  includeStale?: boolean;
};

export type Bbox = [minLng: number, minLat: number, maxLng: number, maxLat: number];

// --- Time helpers -----------------------------------------------------------
// The project standardizes on naive-UTC. DB timestamps are TEXT in ISO form,
// usually WITHOUT a tz offset. JS Date parses an offset-less ISO string as LOCAL
// time, which would drift status by the host's tz. We instead read naive strings
// AS UTC (matching Python), and honor an explicit offset / trailing Z when present.
//
// Returns epoch milliseconds, or null for empty/invalid input. Never throws.
function toEpochMs(value: string | Date | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (value instanceof Date) {
    const t = value.getTime();
    return Number.isNaN(t) ? null : t;
  }
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const s = String(value).trim();
  if (!s) return null;
  // Aware? has a trailing Z or a +HH:MM / -HH:MM offset after the time part.
  const hasTz = /[zZ]$/.test(s) || /[+-]\d{2}:?\d{2}$/.test(s);
  // Normalize a space-separated "YYYY-MM-DD HH:MM:SS" to ISO 'T'.
  const iso = s.includes("T") ? s : s.replace(" ", "T");
  // Naive (no tz) -> treat as UTC by appending Z; aware -> let Date honor offset.
  const t = Date.parse(hasTz ? iso : iso + "Z");
  return Number.isNaN(t) ? null : t;
}

const HOUR_MS = 3600 * 1000;

// naiveLocalIso(d): a "YYYY-MM-DDTHH:MM:SS" string in the HOST's LOCAL wall-clock
// (no tz marker), matching Python's datetime.now().isoformat() that the scraper
// writes. Pass this as `now` to computeStatus so now and last_seen both go through
// the same naive->UTC path; using a Date instead skews the boundary by the host's
// UTC offset. Defaults to current time.
export function naiveLocalIso(d: Date = new Date()): string {
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return (
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` +
    `T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  );
}

// compute_status: pure freshness function. 1:1 with pipeline.compute_status.
// 'expired' if expires_at set & < now; else 'stale' if (now - last_seen) >
// stale_after_hours; else 'active'. now defaults to wall clock.
export function computeStatus(
  expiresAt: string | Date | null | undefined,
  lastSeen: string | Date | null | undefined,
  now: string | Date | number,
  staleAfterHours = 24,
): "active" | "stale" | "expired" {
  const exp = toEpochMs(expiresAt);
  const seen = toEpochMs(lastSeen);
  const nowMs = toEpochMs(now);
  if (nowMs === null) return "active"; // defensive; caller always passes a now
  if (exp !== null && exp < nowMs) return "expired";
  if (seen !== null && nowMs - seen > staleAfterHours * HOUR_MS) return "stale";
  return "active";
}

// --- bbox -------------------------------------------------------------------
// parseBbox: "minLng,minLat,maxLng,maxLat" -> Bbox. Throws on bad input so the
// route can map it to a 400 (mirrors the Python HTTPException(400) cases).
export class BboxError extends Error {}

export function parseBbox(bbox: string | null | undefined): Bbox | null {
  if (!bbox) return null;
  const parts = bbox.split(",").map((p) => Number(p));
  if (parts.length !== 4) {
    throw new BboxError("bbox must be minLng,minLat,maxLng,maxLat");
  }
  // Number("") === 0 and Number("x") === NaN; reject NaN/Infinity so a
  // non-finite bbox is a 400, not a silently-passing comparison.
  if (!parts.every((p) => Number.isFinite(p))) {
    throw new BboxError("bbox values must be finite");
  }
  return parts as Bbox;
}

// inBbox: deal coords inside the (inclusive) bbox. Coordless deals fail. 1:1 with
// Python _in_bbox.
export function inBbox(deal: Pick<Deal, "lat" | "lng">, bbox: Bbox | null): boolean {
  if (bbox === null) return true;
  if (deal.lat === null || deal.lng === null) return false;
  const [minLng, minLat, maxLng, maxLat] = bbox;
  return minLng <= deal.lng && deal.lng <= maxLng && minLat <= deal.lat && deal.lat <= maxLat;
}

// --- dedup collapse ---------------------------------------------------------
// collapseDedup: group by dedup_key; first row seen = primary; later rows' url
// appended to primary.alt_urls (skipping dupes/self). Falsy dedup_key stands
// alone. Mutates primaries' alt_urls. 1:1 with Python _collapse_dedup.
export function collapseDedup(deals: Deal[]): Deal[] {
  const primaryByKey = new Map<string, Deal>();
  const result: Deal[] = [];
  for (const d of deals) {
    const key = d.dedup_key;
    if (!key) {
      result.push(d);
      continue;
    }
    const prim = primaryByKey.get(key);
    if (!prim) {
      primaryByKey.set(key, d);
      result.push(d);
    } else if (!prim.alt_urls.includes(d.url) && d.url !== prim.url) {
      prim.alt_urls.push(d.url);
    }
  }
  return result;
}

// --- JS helpers ported from web/filters.js, list.js, map.js -----------------

// buildQuery(state) -> querystring (no leading "?"). Only truthy filter fields.
// 1:1 with web/filters.js buildQuery (encodeURIComponent semantics preserved).
export function buildQuery(state: FilterState = {}): string {
  const params: string[] = [];
  if (state.type) params.push("type=" + encodeURIComponent(state.type));
  if (state.category) params.push("category=" + encodeURIComponent(state.category));
  if (state.placement) params.push("placement=" + encodeURIComponent(state.placement));
  if (state.bbox) params.push("bbox=" + encodeURIComponent(state.bbox));
  if (state.includeStale) params.push("include_stale=true");
  return params.join("&");
}

// matchesFilters(deal, state): client guard mirroring server filters. Expired
// never matches; stale gated by includeStale; equality on type/category/placement.
export function matchesFilters(
  deal: Pick<Deal, "status" | "deal_type" | "category" | "placement">,
  state: FilterState = {},
): boolean {
  if (deal.status === "expired") return false;
  if (deal.status === "stale" && !state.includeStale) return false;
  if (state.type && deal.deal_type !== state.type) return false;
  if (state.category && deal.category !== state.category) return false;
  if (state.placement && deal.placement !== state.placement) return false;
  return true;
}

// belongsInList(deal): online OR failed-geocode physical (never lost from list).
export function belongsInList(deal: Pick<Deal, "placement" | "geocode_status">): boolean {
  return deal.placement === "online" || deal.geocode_status === "failed";
}

// A Leaflet LatLngBounds-like object: contains([lat, lng]) -> bool.
export type Bounds = { contains(latlng: [number, number]): boolean };

// inViewport(deal, bounds): true if deal has real coords inside bounds. Null
// coords always false. 1:1 with web/map.js inViewport.
export function inViewport(deal: Pick<Deal, "lat" | "lng">, bounds: Bounds): boolean {
  if (deal.lat === null || deal.lng === null) return false;
  return bounds.contains([deal.lat, deal.lng]);
}

// dealsForMap(deals, bounds, state): geocoded physical deals inside the viewport
// that pass the active filters. 1:1 with web/map.js dealsForMap.
export function dealsForMap<T extends Deal>(deals: T[], bounds: Bounds, state: FilterState = {}): T[] {
  return deals.filter(
    (d) => d.placement === "physical" && inViewport(d, bounds) && matchesFilters(d, state),
  );
}

// dealsForList(deals, state): online + failed-geocode physical that pass filters.
// NOT geographically scoped. 1:1 with web/map.js dealsForList.
export function dealsForList<T extends Deal>(deals: T[], state: FilterState = {}): T[] {
  return deals.filter((d) => belongsInList(d) && matchesFilters(d, state));
}
