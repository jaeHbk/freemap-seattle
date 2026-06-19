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

async function fetchDeals() {
  readFilterState();
  filterState.bbox = currentBbox();
  const qs = window.buildQuery(filterState);
  const resp = await fetch("/api/deals?" + qs);
  lastDeals = await resp.json();
  renderMap();
  renderListView();
}

function renderMap() {
  clusterLayer.clearLayers();
  for (const deal of lastDeals) {
    if (deal.placement !== "physical") continue;
    if (deal.lat == null || deal.lng == null) continue;
    if (!window.matchesFilters(deal, filterState)) continue;
    clusterLayer.addLayer(markerFor(deal));
  }
}

function renderListView() {
  const container = document.getElementById("list");
  window.renderList(lastDeals, filterState, container);
}

async function loadFreshness() {
  try {
    const resp = await fetch("/api/meta");
    const meta = await resp.json();
    const times = (meta.sources || [])
      .map((s) => s.last_successful_scrape)
      .filter(Boolean)
      .sort();
    const latest = times.length ? times[times.length - 1] : null;
    document.getElementById("freshness-badge").textContent = latest
      ? "deals as of " + latest.replace("T", " ")
      : "deals as of —";
  } catch (e) {
    document.getElementById("freshness-badge").textContent = "deals as of —";
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
  module.exports = { safeHttpUrl };
}
if (typeof window !== "undefined") {
  window.safeHttpUrl = safeHttpUrl;
}
