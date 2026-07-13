"use client";

import * as React from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.markercluster";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";

import { safeHttpUrl, SEATTLE, SEATTLE_ZOOM } from "@/components/deals";
import type { Deal } from "@/components/deals";
import { TYPE_STYLE, STATUS_LABEL } from "@/components/deal-style";

// SVG path per shape so color is NOT the only signal (a11y). The marker is a
// pin-style teardrop with the shape glyph inset.
function pinSvg(deal: Deal): string {
  const ts = TYPE_STYLE[deal.deal_type] ?? TYPE_STYLE.other;
  const stale = deal.status === "stale";
  const opacity = stale ? 0.5 : 1;
  let glyph: string;
  if (ts.shape === "square") {
    glyph = `<rect x="9" y="6.5" width="8" height="8" rx="1.5" fill="#fff"/>`;
  } else if (ts.shape === "diamond") {
    glyph = `<rect x="9" y="6.5" width="8" height="8" rx="1" fill="#fff" transform="rotate(45 13 10.5)"/>`;
  } else {
    glyph = `<circle cx="13" cy="10.5" r="4.2" fill="#fff"/>`;
  }
  // Static template; deal_type/status are server-enumerated enums, nothing
  // untrusted is interpolated here.
  return `<svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg" style="opacity:${opacity}">
    <path d="M13 0C5.8 0 0 5.7 0 12.8 0 22 13 34 13 34s13-12 13-21.2C26 5.7 20.2 0 13 0z" fill="${ts.color}" stroke="#fff" stroke-width="1.5"/>
    ${glyph}
  </svg>`;
}

// Build the popup as DOM via textContent so scraped title/url/location can never
// inject markup — the XSS-safe approach ported from web/map.js (React escaping
// does not apply to imperative leaflet popups, so we build nodes by hand).
function popupFor(deal: Deal): HTMLElement {
  const ts = TYPE_STYLE[deal.deal_type] ?? TYPE_STYLE.other;
  const root = document.createElement("div");
  root.className = "fm-popup";

  const title = document.createElement("strong");
  title.className = "fm-popup-title";
  title.textContent = deal.title || "";
  root.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "fm-popup-meta";
  meta.textContent = `${ts.label} · ${deal.category} · ${STATUS_LABEL[deal.status]}`;
  root.appendChild(meta);

  if (deal.raw_location) {
    const loc = document.createElement("div");
    loc.className = "fm-popup-loc";
    loc.textContent = deal.raw_location;
    root.appendChild(loc);
  }

  const safeUrl = safeHttpUrl(deal.url);
  if (safeUrl) {
    const link = document.createElement("a");
    link.href = safeUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "fm-popup-link";
    link.textContent = "View deal →";
    root.appendChild(link);
  } else {
    const plain = document.createElement("span");
    plain.className = "fm-popup-loc";
    plain.textContent = "View deal (link unavailable)";
    root.appendChild(plain);
  }

  return root;
}

function ClusterLayer({ deals }: { deals: Deal[] }) {
  const map = useMap();
  const groupRef = React.useRef<L.MarkerClusterGroup | null>(null);

  React.useEffect(() => {
    // L.markerClusterGroup is added by the markercluster plugin import.
    const group = (L as unknown as { markerClusterGroup: (o?: object) => L.MarkerClusterGroup })
      .markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50 });
    groupRef.current = group;
    map.addLayer(group);
    return () => {
      map.removeLayer(group);
      groupRef.current = null;
    };
  }, [map]);

  React.useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    group.clearLayers();
    for (const deal of deals) {
      if (deal.lat == null || deal.lng == null) continue;
      const icon = L.divIcon({
        className: "fm-pin",
        html: pinSvg(deal),
        iconSize: [26, 34],
        iconAnchor: [13, 34],
        popupAnchor: [0, -30],
      });
      const marker = L.marker([deal.lat, deal.lng], {
        icon,
        title: deal.title,
        alt: `${TYPE_STYLE[deal.deal_type]?.label ?? "Deal"}: ${deal.title}`,
      });
      marker.bindPopup(popupFor(deal), { closeButton: true, maxWidth: 280 });
      group.addLayer(marker);
    }
  }, [deals]);

  return null;
}

export default function DealMapInner({ deals }: { deals: Deal[] }) {
  return (
    <MapContainer
      center={SEATTLE}
      zoom={SEATTLE_ZOOM}
      scrollWheelZoom
      className="size-full"
      style={{ background: "var(--map-bg)" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={19}
      />
      <ClusterLayer deals={deals} />
    </MapContainer>
  );
}
