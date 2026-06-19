// map.js — orchestrates the FreeMap UI: Leaflet map, bbox fetch on moveend,
// clustered colored pins, list view, filters, and the freshness badge.

const PIN_COLORS = { free: "#1a9850", bogo: "#3b82f6", other: "#9ca3af" };
const SEATTLE = [47.6062, -122.3321];

const filterState = { type: "", category: "", placement: "", bbox: "", includeStale: false };

let map;
let clusterLayer;
let lastDeals = [];

function readFilterState() {
  filterState.type = document.getElementById("filter-type").value;
  filterState.category = document.getElementById("filter-category").value;
  filterState.includeStale = document.getElementById("filter-stale").checked;
}

function currentBbox() {
  const b = map.getBounds();
  // minLng,minLat,maxLng,maxLat
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
}

// safeHttpUrl(u) -> u if it is an http(s) URL, else null. Deal data is scraped
// from UNTRUSTED sources, so we never emit javascript:/data:/etc. as an href.
function safeHttpUrl(u) {
  if (typeof u !== "string") return null;
  return /^https?:\/\//i.test(u.trim()) ? u.trim() : null;
}

function markerFor(deal) {
  const color = PIN_COLORS[deal.deal_type] || PIN_COLORS.other;
  const stale = deal.status === "stale";
  // deal_type/status are server-enumerated, but the dot is built from a fixed
  // template; nothing untrusted is interpolated into the divIcon HTML.
  const icon = L.divIcon({
    className: "deal-pin" + (stale ? " stale" : ""),
    html: `<span class="pin-dot" style="background:${color};opacity:${stale ? 0.4 : 1}"></span>`,
    iconSize: [16, 16],
  });
  const marker = L.marker([deal.lat, deal.lng], { icon });

  // Build the popup as DOM (textContent) so scraped title/url can never inject
  // markup or scripts — mirrors the XSS-safe approach in list.js.
  const root = document.createElement("div");

  const title = document.createElement("strong");
  title.textContent = deal.title || "";
  root.appendChild(title);
  root.appendChild(document.createElement("br"));

  const meta = document.createElement("span");
  meta.textContent = `${deal.deal_type} · ${deal.category} · ${deal.status}`;
  root.appendChild(meta);
  root.appendChild(document.createElement("br"));

  const safeUrl = safeHttpUrl(deal.url);
  if (safeUrl) {
    const link = document.createElement("a");
    link.href = safeUrl;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "View deal";
    root.appendChild(link);
  } else {
    const plain = document.createElement("span");
    plain.textContent = "View deal (link unavailable)";
    root.appendChild(plain);
  }

  const altUrls = (deal.alt_urls || []).map(safeHttpUrl).filter(Boolean);
  altUrls.forEach((u, i) => {
    root.appendChild(document.createElement("br"));
    const alt = document.createElement("a");
    alt.href = u;
    alt.target = "_blank";
    alt.rel = "noopener";
    alt.textContent = "alt " + (i + 1);
    root.appendChild(alt);
  });

  marker.bindPopup(root);
  return marker;
}

// --- Map/list partition (pure, node-testable) -------------------------------
// The spec splits deals two ways: the MAP shows geocoded physical deals inside
// the current viewport; the LIST shows online + failed-geocode physical deals
// (web/list.js belongsInList). A deal belongs to exactly one set, never both.
//
// The frontend fetches deals WITHOUT a bbox so the API returns coordless deals
// (online / failed-geocode) too — the old "always send bbox" path dropped them
// server-side, leaving the list view permanently empty. The map is instead
// scoped to the viewport CLIENT-SIDE here.

function _matchesFilters(deal, state) {
  const fn = (typeof window !== "undefined" && window.matchesFilters) || _mf;
  return fn(deal, state);
}
function _belongsInList(deal) {
  const fn = (typeof window !== "undefined" && window.belongsInList) || _bil;
  return fn(deal);
}
// Lazy node fallbacks so map.js is requirable without a browser.
let _mf = null;
let _bil = null;
if (typeof window === "undefined" && typeof require !== "undefined") {
  try { _mf = require("./filters.js").matchesFilters; } catch (e) { /* optional */ }
  try { _bil = require("./list.js").belongsInList; } catch (e) { /* optional */ }
}

// inViewport(deal, bounds) -> true if the deal has real coords inside `bounds`
// (a Leaflet LatLngBounds-like object exposing contains([lat, lng])).
function inViewport(deal, bounds) {
  if (deal.lat == null || deal.lng == null) return false;
  return bounds.contains([deal.lat, deal.lng]);
}

// dealsForMap(deals, bounds, state) -> geocoded physical deals inside the
// viewport that pass the active filters.
function dealsForMap(deals, bounds, state) {
  return deals.filter(
    (d) =>
      d.placement === "physical" &&
      inViewport(d, bounds) &&
      _matchesFilters(d, state)
  );
}

// dealsForList(deals, state) -> online + failed-geocode physical deals that pass
// the active filters. NOT geographically scoped (the list is not a map view).
function dealsForList(deals, state) {
  return deals.filter((d) => _belongsInList(d) && _matchesFilters(d, state));
}

async function fetchDeals() {
  readFilterState();
  // Intentionally NO bbox: the API excludes coordless deals when a bbox is
  // present, which would hide every online / failed-geocode deal from the list.
  // We scope the MAP to the viewport client-side in renderMap() instead.
  filterState.bbox = "";
  const qs = window.buildQuery(filterState);
  const resp = await fetch("/api/deals?" + qs);
  lastDeals = await resp.json();
  renderMap();
  renderListView();
}

function renderMap() {
  clusterLayer.clearLayers();
  const bounds = map.getBounds();
  for (const deal of dealsForMap(lastDeals, bounds, filterState)) {
    clusterLayer.addLayer(markerFor(deal));
  }
}

function renderListView() {
  const container = document.getElementById("list");
  // renderList itself filters by belongsInList + matchesFilters, mirroring
  // dealsForList; pass the full set so coordless deals reach the list.
  window.renderList(lastDeals, filterState, container);
}

async function loadFreshness(retriesLeft = 3) {
  const badge = document.getElementById("freshness-badge");
  try {
    const resp = await fetch("/api/meta");
    if (!resp.ok) throw new Error("meta HTTP " + resp.status);
    const meta = await resp.json();
    const times = (meta.sources || [])
      .map((s) => s.last_successful_scrape)
      .filter(Boolean)
      .sort();
    const latest = times.length ? times[times.length - 1] : null;
    badge.textContent = latest
      ? "deals as of " + latest.replace("T", " ")
      : "deals as of —";
  } catch (e) {
    // A transient failure (e.g. server still warming up on first paint) must not
    // latch "—" forever — retry a few times with backoff before giving up.
    if (retriesLeft > 0) {
      badge.textContent = "deals as of …";
      setTimeout(() => loadFreshness(retriesLeft - 1), 1000);
    } else {
      badge.textContent = "deals as of —";
    }
  }
}

function showView(which) {
  const mapView = document.getElementById("map-view");
  const listView = document.getElementById("list-view");
  const btnMap = document.getElementById("btn-map");
  const btnList = document.getElementById("btn-list");
  const isMap = which === "map";
  mapView.hidden = !isMap;
  listView.hidden = isMap;
  btnMap.classList.toggle("active", isMap);
  btnList.classList.toggle("active", !isMap);
  if (isMap) map.invalidateSize();
}

function init() {
  map = L.map("map").setView(SEATTLE, 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  clusterLayer = L.markerClusterGroup();
  map.addLayer(clusterLayer);

  map.on("moveend", fetchDeals);

  document.getElementById("filter-type").addEventListener("change", fetchDeals);
  document.getElementById("filter-category").addEventListener("change", fetchDeals);
  document.getElementById("filter-stale").addEventListener("change", fetchDeals);
  document.getElementById("btn-map").addEventListener("click", () => showView("map"));
  document.getElementById("btn-list").addEventListener("click", () => showView("list"));

  loadFreshness();
  fetchDeals(); // initial load (moveend may not fire on first render)
}

// Wire up only in a real browser. Guarded so the pure helpers (e.g. safeHttpUrl)
// can be required in Node-run unit tests where `document` does not exist.
if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", init);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { safeHttpUrl, inViewport, dealsForMap, dealsForList };
}
if (typeof window !== "undefined") {
  window.safeHttpUrl = safeHttpUrl;
  window.inViewport = inViewport;
  window.dealsForMap = dealsForMap;
  window.dealsForList = dealsForList;
}
