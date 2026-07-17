import * as React from "react";
import maplibregl, {
  type GeoJSONSource,
  type MapLayerMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  dealsToFeatureCollection,
  OPENFREEMAP_STYLE_URL,
} from "@/components/deal-map-data";
import { TYPE_STYLE, STATUS_LABEL } from "@/components/deal-style";
import { safeHttpUrl, SEATTLE, SEATTLE_ZOOM } from "@/components/deals";
import type { Deal } from "@/components/deals";
import type { SearchOrigin } from "@/lib/location";
import type { MapViewport } from "@/lib/url-state";

const DEAL_SOURCE_ID = "freemap-deals";
const CLUSTER_LAYER_ID = "freemap-deal-clusters";
const CLUSTER_COUNT_LAYER_ID = "freemap-deal-cluster-counts";
const PIN_LAYER_ID = "freemap-deal-pins";

const PIN_IMAGE_IDS = {
  free: "freemap-pin-free",
  bogo: "freemap-pin-bogo",
  other: "freemap-pin-other",
} as const;

function createPinImage(
  color: string,
  shape: "circle" | "square" | "diamond",
): ImageData {
  const pixelRatio = 2;
  const canvas = document.createElement("canvas");
  canvas.width = 26 * pixelRatio;
  canvas.height = 34 * pixelRatio;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D rendering is unavailable.");

  context.scale(pixelRatio, pixelRatio);
  context.beginPath();
  context.moveTo(13, 0.75);
  context.bezierCurveTo(5.9, 0.75, 0.75, 6.2, 0.75, 12.8);
  context.bezierCurveTo(0.75, 21.4, 13, 33, 13, 33);
  context.bezierCurveTo(13, 33, 25.25, 21.4, 25.25, 12.8);
  context.bezierCurveTo(25.25, 6.2, 20.1, 0.75, 13, 0.75);
  context.closePath();
  context.shadowColor = "rgb(0 0 0 / 0.3)";
  context.shadowBlur = 3;
  context.shadowOffsetY = 2;
  context.fillStyle = color;
  context.fill();
  context.shadowColor = "transparent";
  context.lineWidth = 1.5;
  context.strokeStyle = "#ffffff";
  context.stroke();

  context.fillStyle = "#ffffff";
  if (shape === "square") {
    context.beginPath();
    context.roundRect(9, 6.5, 8, 8, 1.5);
    context.fill();
  } else if (shape === "diamond") {
    context.save();
    context.translate(13, 10.5);
    context.rotate(Math.PI / 4);
    context.beginPath();
    context.roundRect(-4, -4, 8, 8, 1);
    context.fill();
    context.restore();
  } else {
    context.beginPath();
    context.arc(13, 10.5, 4.2, 0, Math.PI * 2);
    context.fill();
  }

  return context.getImageData(0, 0, canvas.width, canvas.height);
}

function addPinImages(map: maplibregl.Map) {
  for (const [dealType, imageId] of Object.entries(PIN_IMAGE_IDS)) {
    if (map.hasImage(imageId)) continue;
    const style = TYPE_STYLE[dealType as keyof typeof TYPE_STYLE];
    map.addImage(imageId, createPinImage(style.color, style.shape), {
      pixelRatio: 2,
    });
  }
}

// Build popup DOM with textContent so scraped fields can never inject markup.
function popupFor(deal: Deal, onViewDetails: () => void): HTMLElement {
  const typeStyle = TYPE_STYLE[deal.deal_type] ?? TYPE_STYLE.other;
  const root = document.createElement("div");
  root.className = "fm-popup";

  const title = document.createElement("strong");
  title.className = "fm-popup-title";
  title.textContent = deal.title || "";
  root.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "fm-popup-meta";
  meta.textContent = `${typeStyle.label} · ${deal.category} · ${STATUS_LABEL[deal.status]}`;
  root.appendChild(meta);

  if (deal.raw_location) {
    const location = document.createElement("div");
    location.className = "fm-popup-loc";
    location.textContent = deal.raw_location;
    root.appendChild(location);
  }

  const actions = document.createElement("div");
  actions.className = "fm-popup-actions";

  const detailButton = document.createElement("button");
  detailButton.type = "button";
  detailButton.className = "fm-popup-detail";
  detailButton.textContent = "Details";
  detailButton.addEventListener("click", onViewDetails);
  actions.appendChild(detailButton);

  const safeUrl = safeHttpUrl(deal.url);
  if (safeUrl) {
    const link = document.createElement("a");
    link.href = safeUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "fm-popup-link";
    link.textContent = "View deal";
    actions.appendChild(link);
  } else {
    const unavailable = document.createElement("span");
    unavailable.className = "fm-popup-loc";
    unavailable.textContent = "Deal link unavailable";
    actions.appendChild(unavailable);
  }
  root.appendChild(actions);

  return root;
}

function addDealLayers(map: maplibregl.Map, deals: Deal[]) {
  addPinImages(map);
  map.addSource(DEAL_SOURCE_ID, {
    type: "geojson",
    data: dealsToFeatureCollection(deals),
    cluster: true,
    clusterMaxZoom: 14,
    clusterRadius: 50,
  });

  map.addLayer({
    id: CLUSTER_LAYER_ID,
    type: "circle",
    source: DEAL_SOURCE_ID,
    filter: ["has", "point_count"],
    paint: {
      "circle-color": [
        "step",
        ["get", "point_count"],
        "#1f7a4d",
        10,
        "#0e7490",
        25,
        "#b45309",
      ],
      "circle-radius": [
        "step",
        ["get", "point_count"],
        20,
        10,
        24,
        25,
        29,
      ],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 3,
      "circle-opacity": 0.94,
    },
  });

  map.addLayer({
    id: CLUSTER_COUNT_LAYER_ID,
    type: "symbol",
    source: DEAL_SOURCE_ID,
    filter: ["has", "point_count"],
    layout: {
      "text-field": ["get", "point_count_abbreviated"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 13,
      "text-allow-overlap": true,
    },
    paint: {
      "text-color": "#ffffff",
      "text-halo-color": "rgb(0 0 0 / 0.18)",
      "text-halo-width": 1,
    },
  });

  map.addLayer({
    id: PIN_LAYER_ID,
    type: "symbol",
    source: DEAL_SOURCE_ID,
    filter: ["!", ["has", "point_count"]],
    layout: {
      "icon-image": [
        "match",
        ["get", "dealType"],
        "free",
        PIN_IMAGE_IDS.free,
        "bogo",
        PIN_IMAGE_IDS.bogo,
        PIN_IMAGE_IDS.other,
      ],
      "icon-anchor": "bottom",
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
    },
    paint: {
      "icon-opacity": [
        "case",
        ["==", ["get", "status"], "stale"],
        0.5,
        1,
      ],
    },
  });
}

type PointFeatureLike = {
  geometry: { type: string; coordinates?: unknown };
};

function pointCoordinates(
  feature: PointFeatureLike | undefined,
): [number, number] | null {
  const geometry = feature?.geometry;
  if (!geometry || geometry.type !== "Point") return null;
  const coordinates = geometry.coordinates as number[] | undefined;
  if (
    !coordinates ||
    !Number.isFinite(coordinates[0]) ||
    !Number.isFinite(coordinates[1])
  ) {
    return null;
  }
  return [coordinates[0], coordinates[1]];
}

interface DealMapInnerProps {
  deals: Deal[];
  origin: SearchOrigin | null;
  selectedDealId: string | null;
  viewport: MapViewport | null;
  onSelectDeal: (dealId: string) => void;
  onViewDetails: (dealId: string) => void;
  onViewportChange: (viewport: MapViewport) => void;
  onInitializationError?: (message: string) => void;
}

export default function DealMapInner({
  deals,
  origin,
  selectedDealId,
  viewport,
  onSelectDeal,
  onViewDetails,
  onViewportChange,
  onInitializationError,
}: DealMapInnerProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const mapRef = React.useRef<maplibregl.Map | null>(null);
  const popupRef = React.useRef<maplibregl.Popup | null>(null);
  const originMarkerRef = React.useRef<maplibregl.Marker | null>(null);
  const dealsRef = React.useRef(deals);
  const originRef = React.useRef(origin);
  const selectedDealIdRef = React.useRef(selectedDealId);
  const viewportRef = React.useRef(viewport);
  const onSelectDealRef = React.useRef(onSelectDeal);
  const onViewDetailsRef = React.useRef(onViewDetails);
  const onViewportChangeRef = React.useRef(onViewportChange);
  const dealsByIdRef = React.useRef(
    new Map(deals.map((deal) => [String(deal.id), deal])),
  );
  const syncDealTargetsRef = React.useRef<() => void>(() => {});
  const focusOriginRef = React.useRef<
    (origin: SearchOrigin | null, moveCamera?: boolean) => void
  >(() => {});
  const openSelectedDealRef = React.useRef<
    (dealId: string | null, moveCamera?: boolean) => void
  >(() => {});

  React.useEffect(() => {
    originRef.current = origin;
    selectedDealIdRef.current = selectedDealId;
    viewportRef.current = viewport;
    onSelectDealRef.current = onSelectDeal;
    onViewDetailsRef.current = onViewDetails;
    onViewportChangeRef.current = onViewportChange;
  }, [
    onSelectDeal,
    onViewDetails,
    onViewportChange,
    origin,
    selectedDealId,
    viewport,
  ]);

  React.useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    let mapSettled = false;
    let map: maplibregl.Map;
    const initialViewport = viewportRef.current;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: OPENFREEMAP_STYLE_URL,
        center: initialViewport
          ? [initialViewport.lng, initialViewport.lat]
          : [SEATTLE[1], SEATTLE[0]],
        zoom: initialViewport?.zoom ?? SEATTLE_ZOOM,
        minZoom: 8,
        maxZoom: 19,
        pitchWithRotate: false,
        dragRotate: false,
        touchPitch: false,
        attributionControl: false,
        canvasContextAttributes: { antialias: true },
      });
    } catch (error) {
      onInitializationError?.(
        error instanceof Error ? error.message : "The map could not start.",
      );
      return;
    }
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();

    map.addControl(
      new maplibregl.NavigationControl({
        showCompass: false,
        showZoom: true,
      }),
      "top-right",
    );
    map.addControl(
      new maplibregl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        fitBoundsOptions: { maxZoom: 14, animate: !reducedMotion },
        trackUserLocation: false,
        showAccuracyCircle: true,
        showUserLocation: true,
      }),
      "top-right",
    );
    map.addControl(
      new maplibregl.AttributionControl({
        compact: true,
      }),
      "bottom-right",
    );

    const dealTargets = new Map<
      string,
      { marker: maplibregl.Marker; element: HTMLButtonElement }
    >();

    const expandClusterAt = (
      clusterId: number,
      coordinates: [number, number],
    ) => {
      const source = map.getSource(DEAL_SOURCE_ID) as
        | GeoJSONSource
        | undefined;
      if (!source || !Number.isFinite(clusterId)) return;

      void source
        .getClusterExpansionZoom(clusterId)
        .then((zoom) => {
          map.easeTo({
            center: coordinates,
            zoom,
            duration: reducedMotion ? 0 : 500,
          });
        })
        .catch(() => {});
    };

    const openDealAt = (deal: Deal, coordinates: [number, number]) => {
      onSelectDealRef.current(String(deal.id));
      popupRef.current?.remove();
      popupRef.current = new maplibregl.Popup({
        closeButton: true,
        closeOnClick: true,
        focusAfterOpen: true,
        maxWidth: "300px",
        offset: 26,
      })
        .setLngLat(coordinates)
        .setDOMContent(
          popupFor(deal, () => onViewDetailsRef.current(String(deal.id))),
        )
        .addTo(map);
    };

    const focusOrigin = (
      nextOrigin: SearchOrigin | null,
      moveCamera = true,
    ) => {
      originMarkerRef.current?.remove();
      originMarkerRef.current = null;
      if (!nextOrigin) return;

      const markerElement = document.createElement("div");
      markerElement.className = "fm-search-origin";
      markerElement.setAttribute("aria-label", nextOrigin.label);
      markerElement.title = nextOrigin.label;
      originMarkerRef.current = new maplibregl.Marker({
        element: markerElement,
        anchor: "center",
      })
        .setLngLat([nextOrigin.lng, nextOrigin.lat])
        .addTo(map);
      if (moveCamera) {
        map.easeTo({
          center: [nextOrigin.lng, nextOrigin.lat],
          zoom: Math.max(map.getZoom(), 13),
          duration: reducedMotion ? 0 : 600,
        });
      }
    };
    focusOriginRef.current = focusOrigin;

    const openSelectedDeal = (
      dealId: string | null,
      moveCamera = true,
    ) => {
      if (!dealId) {
        popupRef.current?.remove();
        popupRef.current = null;
        return;
      }
      const deal = dealsByIdRef.current.get(dealId);
      if (deal?.lat == null || deal.lng == null) return;
      const coordinates: [number, number] = [deal.lng, deal.lat];
      if (moveCamera) {
        map.easeTo({
          center: coordinates,
          zoom: Math.max(map.getZoom(), 15),
          duration: reducedMotion ? 0 : 500,
        });
      }
      openDealAt(deal, coordinates);
    };
    openSelectedDealRef.current = openSelectedDeal;

    const reportViewport = () => {
      const center = map.getCenter();
      onViewportChangeRef.current({
        lat: center.lat,
        lng: center.lng,
        zoom: map.getZoom(),
      });
    };

    const expandCluster = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const coordinates = pointCoordinates(feature);
      const clusterId = Number(feature?.properties?.cluster_id);
      if (!coordinates) return;
      expandClusterAt(clusterId, coordinates);
    };

    const openDeal = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const coordinates = pointCoordinates(feature);
      const dealId = String(feature?.properties?.dealId ?? "");
      const deal = dealsByIdRef.current.get(dealId);
      if (!deal || !coordinates) return;
      openDealAt(deal, coordinates);
    };

    const syncDealTargets = () => {
      const bounds = map.getBounds();
      const visibleDealIds = new Set<string>();
      for (const deal of dealsRef.current) {
        if (
          deal.lat == null ||
          deal.lng == null ||
          !bounds.contains([deal.lng, deal.lat])
        ) {
          continue;
        }
        const dealId = String(deal.id);
        const coordinates: [number, number] = [deal.lng, deal.lat];
        visibleDealIds.add(dealId);

        const label = `${TYPE_STYLE[deal.deal_type]?.label ?? "Deal"}: ${deal.title}, ${STATUS_LABEL[deal.status]}`;
        const existing = dealTargets.get(dealId);
        if (existing) {
          existing.element.setAttribute("aria-label", label);
          existing.element.title = deal.title;
          existing.marker.setLngLat(coordinates);
          continue;
        }

        const element = document.createElement("button");
        element.type = "button";
        element.className = "fm-map-target fm-map-target-pin";
        element.dataset.mapDealTarget = dealId;
        element.setAttribute("aria-label", label);
        element.title = deal.title;
        const marker = new maplibregl.Marker({
          element,
          anchor: "bottom",
        })
          .setLngLat(coordinates)
          .addTo(map);
        element.addEventListener("click", (domEvent) => {
          domEvent.stopPropagation();
          const currentDeal = dealsByIdRef.current.get(dealId);
          if (currentDeal?.lat == null || currentDeal.lng == null) return;
          openDealAt(currentDeal, [currentDeal.lng, currentDeal.lat]);
        });
        dealTargets.set(dealId, { marker, element });
      }

      for (const [dealId, target] of dealTargets) {
        if (visibleDealIds.has(dealId)) continue;
        target.marker.remove();
        dealTargets.delete(dealId);
      }
    };
    syncDealTargetsRef.current = syncDealTargets;

    map.once("load", () => {
      if (mapRef.current !== map) return;
      mapSettled = true;
      addDealLayers(map, dealsRef.current);
      const canvas = map.getCanvas();
      canvas.setAttribute(
        "aria-label",
        `Interactive map showing ${dealsRef.current.length} mapped deals`,
      );
      syncDealTargets();
      focusOrigin(originRef.current, !initialViewport);
      openSelectedDeal(selectedDealIdRef.current, !initialViewport);
      if (
        initialViewport ||
        (!originRef.current && !selectedDealIdRef.current)
      ) {
        reportViewport();
      }
    });

    const showPointer = () => {
      map.getCanvas().style.cursor = "pointer";
    };
    const clearPointer = () => {
      map.getCanvas().style.cursor = "";
    };

    map.on("click", CLUSTER_LAYER_ID, expandCluster);
    map.on("click", PIN_LAYER_ID, openDeal);
    map.on("mouseenter", CLUSTER_LAYER_ID, showPointer);
    map.on("mouseleave", CLUSTER_LAYER_ID, clearPointer);
    map.on("mouseenter", PIN_LAYER_ID, showPointer);
    map.on("mouseleave", PIN_LAYER_ID, clearPointer);
    map.on("moveend", () => {
      syncDealTargets();
      reportViewport();
    });
    map.on("resize", syncDealTargets);
    map.on("error", (event) => {
      if (mapRef.current !== map || mapSettled) return;
      if ((event as { sourceId?: string }).sourceId) return;
      mapSettled = true;
      onInitializationError?.(
        event.error?.message ?? "The map could not load.",
      );
    });

    return () => {
      popupRef.current?.remove();
      popupRef.current = null;
      originMarkerRef.current?.remove();
      originMarkerRef.current = null;
      syncDealTargetsRef.current = () => {};
      focusOriginRef.current = () => {};
      openSelectedDealRef.current = () => {};
      for (const target of dealTargets.values()) target.marker.remove();
      mapRef.current = null;
      map.remove();
    };
  }, [onInitializationError]);

  React.useEffect(() => {
    focusOriginRef.current(origin, false);
  }, [origin]);

  React.useEffect(() => {
    openSelectedDealRef.current(selectedDealId, false);
  }, [selectedDealId]);

  React.useEffect(() => {
    viewportRef.current = viewport;
    const map = mapRef.current;
    if (!map || !viewport) return;
    const center = map.getCenter();
    if (
      Math.abs(center.lat - viewport.lat) < 0.00001 &&
      Math.abs(center.lng - viewport.lng) < 0.00001 &&
      Math.abs(map.getZoom() - viewport.zoom) < 0.01
    ) {
      return;
    }
    map.jumpTo({
      center: [viewport.lng, viewport.lat],
      zoom: viewport.zoom,
    });
  }, [viewport]);

  React.useEffect(() => {
    dealsRef.current = deals;
    dealsByIdRef.current = new Map(
      deals.map((deal) => [String(deal.id), deal]),
    );

    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(DEAL_SOURCE_ID) as GeoJSONSource | undefined;
    source?.setData(dealsToFeatureCollection(deals));
    syncDealTargetsRef.current();
    map
      .getCanvas()
      .setAttribute(
        "aria-label",
        `Interactive map showing ${deals.length} mapped deals`,
      );
  }, [deals]);

  return (
    <div
      ref={containerRef}
      className="size-full"
      data-map-provider="openfreemap"
      aria-label="Interactive Seattle deals map"
    />
  );
}
