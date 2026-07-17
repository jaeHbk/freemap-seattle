import type { FilterState } from "@/components/deals";
import type { ViewValue } from "@/components/ViewTabs";
import type { SearchOrigin } from "@/lib/location";

export interface MapViewport {
  lat: number;
  lng: number;
  zoom: number;
}

export interface AppUrlState {
  view: ViewValue;
  filters: FilterState;
  origin: SearchOrigin | null;
  selectedDealId: string | null;
  detailsOpen: boolean;
  mapViewport: MapViewport | null;
}

export const DEFAULT_URL_STATE: AppUrlState = {
  view: "map",
  filters: {
    type: "",
    category: "",
    placement: "",
    includeStale: false,
  },
  origin: null,
  selectedDealId: null,
  detailsOpen: false,
  mapViewport: null,
};

const OWNED_PARAMS = [
  "view",
  "type",
  "category",
  "placement",
  "stale",
  "origin",
  "origin_label",
  "origin_source",
  "deal",
  "details",
  "map",
] as const;

function enumValue<T extends string>(
  value: string | null,
  choices: readonly T[],
  fallback: T,
): T {
  return value && choices.includes(value as T) ? (value as T) : fallback;
}

function coordinates(value: string | null): [number, number] | null {
  const parts = value?.split(",");
  if (parts?.length !== 2) return null;
  const lat = Number(parts[0]);
  const lng = Number(parts[1]);
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lng) ||
    lat < -90 ||
    lat > 90 ||
    lng < -180 ||
    lng > 180
  ) {
    return null;
  }
  return [lat, lng];
}

function dealId(value: string | null): string | null {
  const trimmed = value?.trim() ?? "";
  return /^[A-Za-z0-9._:-]{1,128}$/.test(trimmed) ? trimmed : null;
}

export function parseUrlState(params: URLSearchParams): AppUrlState {
  const originCoordinates = coordinates(params.get("origin"));
  const originLabel = params.get("origin_label")?.trim().slice(0, 120);
  const origin =
    originCoordinates && originLabel
      ? {
          lat: originCoordinates[0],
          lng: originCoordinates[1],
          label: originLabel,
          source: enumValue(
            params.get("origin_source"),
            ["search", "geolocation"] as const,
            "search",
          ),
        }
      : null;

  const mapParts = params.get("map")?.split(",");
  const mapCoordinates =
    mapParts?.length === 3
      ? coordinates(`${mapParts[0]},${mapParts[1]}`)
      : null;
  const zoom = mapParts?.length === 3 ? Number(mapParts[2]) : Number.NaN;
  const mapViewport =
    mapCoordinates && Number.isFinite(zoom) && zoom >= 8 && zoom <= 19
      ? { lat: mapCoordinates[0], lng: mapCoordinates[1], zoom }
      : null;

  const selectedDealId = dealId(params.get("deal"));
  return {
    view: enumValue(params.get("view"), ["map", "list"] as const, "map"),
    filters: {
      type: enumValue(
        params.get("type"),
        ["", "free", "bogo", "other"] as const,
        "",
      ),
      category: enumValue(
        params.get("category"),
        ["", "food", "retail", "event", "other"] as const,
        "",
      ),
      placement: enumValue(
        params.get("placement"),
        ["", "physical", "online"] as const,
        "",
      ),
      includeStale: params.get("stale") === "1",
    },
    origin,
    selectedDealId,
    detailsOpen: Boolean(selectedDealId && params.get("details") === "1"),
    mapViewport,
  };
}

function fixed(value: number, digits: number): string {
  return Number(value.toFixed(digits)).toString();
}

export function serializeUrlState(
  state: AppUrlState,
  existing = new URLSearchParams(),
): URLSearchParams {
  const params = new URLSearchParams(existing);
  for (const key of OWNED_PARAMS) params.delete(key);

  if (state.view !== "map") params.set("view", state.view);
  if (state.filters.type) params.set("type", state.filters.type);
  if (state.filters.category) params.set("category", state.filters.category);
  if (state.filters.placement) {
    params.set("placement", state.filters.placement);
  }
  if (state.filters.includeStale) params.set("stale", "1");

  if (state.origin) {
    params.set(
      "origin",
      `${fixed(state.origin.lat, 5)},${fixed(state.origin.lng, 5)}`,
    );
    params.set("origin_label", state.origin.label.slice(0, 120));
    if (state.origin.source !== "search") {
      params.set("origin_source", state.origin.source);
    }
  }

  if (state.selectedDealId) {
    params.set("deal", state.selectedDealId);
    if (state.detailsOpen) params.set("details", "1");
  }

  if (state.mapViewport) {
    params.set(
      "map",
      [
        fixed(state.mapViewport.lat, 5),
        fixed(state.mapViewport.lng, 5),
        fixed(state.mapViewport.zoom, 2),
      ].join(","),
    );
  }

  return params;
}
