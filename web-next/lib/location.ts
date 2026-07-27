import type { Deal } from "@/components/deals";
import {
  isInMarketArea,
  MARKETS,
  type Market,
} from "./markets.ts";

export interface SearchOrigin {
  lat: number;
  lng: number;
  label: string;
  source: "search" | "geolocation";
}

export interface Neighborhood {
  name: string;
  aliases?: string[];
  lat: number;
  lng: number;
}

export const SEATTLE_NEIGHBORHOODS: readonly Neighborhood[] = [
  { name: "Ballard", lat: 47.6687, lng: -122.386 },
  { name: "Beacon Hill", lat: 47.5795, lng: -122.3116 },
  { name: "Belltown", lat: 47.6141, lng: -122.345 },
  { name: "Capitol Hill", lat: 47.6231, lng: -122.3165 },
  { name: "Central District", aliases: ["CD"], lat: 47.6088, lng: -122.2968 },
  { name: "Columbia City", lat: 47.5599, lng: -122.2869 },
  { name: "Downtown", lat: 47.6062, lng: -122.3321 },
  { name: "Fremont", lat: 47.651, lng: -122.3504 },
  { name: "Georgetown", lat: 47.5487, lng: -122.3206 },
  { name: "Green Lake", aliases: ["Greenlake"], lat: 47.6798, lng: -122.3258 },
  { name: "Lake City", lat: 47.7193, lng: -122.2957 },
  { name: "Madison Park", lat: 47.6359, lng: -122.2797 },
  { name: "Magnolia", lat: 47.649, lng: -122.4017 },
  { name: "Northgate", lat: 47.7086, lng: -122.3258 },
  { name: "Pioneer Square", lat: 47.6017, lng: -122.3339 },
  { name: "Queen Anne", lat: 47.6375, lng: -122.3565 },
  { name: "Rainier Beach", lat: 47.5223, lng: -122.2796 },
  { name: "South Lake Union", aliases: ["SLU"], lat: 47.6233, lng: -122.3376 },
  { name: "University District", aliases: ["U District"], lat: 47.6614, lng: -122.3132 },
  { name: "Wallingford", lat: 47.6615, lng: -122.3343 },
  { name: "West Seattle", lat: 47.5611, lng: -122.3868 },
] as const;

export const ATLANTA_NEIGHBORHOODS: readonly Neighborhood[] = [
  { name: "Buckhead", lat: 33.8381, lng: -84.3797 },
  { name: "Downtown", lat: 33.7557, lng: -84.3884 },
  { name: "East Atlanta Village", aliases: ["EAV"], lat: 33.7407, lng: -84.3452 },
  { name: "Grant Park", lat: 33.7372, lng: -84.3681 },
  { name: "Inman Park", lat: 33.7576, lng: -84.3622 },
  { name: "Little Five Points", aliases: ["L5P"], lat: 33.7651, lng: -84.3499 },
  { name: "Midtown", lat: 33.7833, lng: -84.3831 },
  { name: "Old Fourth Ward", aliases: ["O4W"], lat: 33.7641, lng: -84.3713 },
  { name: "Virginia-Highland", aliases: ["Virginia Highland", "VaHi"], lat: 33.7821, lng: -84.3537 },
  { name: "West Midtown", lat: 33.7868, lng: -84.4113 },
] as const;

export const NEIGHBORHOODS_BY_MARKET: Record<
  Market,
  readonly Neighborhood[]
> = {
  seattle: SEATTLE_NEIGHBORHOODS,
  atlanta: ATLANTA_NEIGHBORHOODS,
};

function normalizePlace(value: string): string {
  return value
    .toLowerCase()
    .replace(/\b(seattle|washington|atlanta|georgia|wa|ga|usa)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function resolveNeighborhood(
  query: string,
  market: Market,
): SearchOrigin | null {
  const normalized = normalizePlace(query);
  if (!normalized) return null;
  const match = NEIGHBORHOODS_BY_MARKET[market].find((neighborhood) =>
    [neighborhood.name, ...(neighborhood.aliases ?? [])].some(
      (name) => normalizePlace(name) === normalized,
    ),
  );
  if (!match) return null;
  return {
    lat: match.lat,
    lng: match.lng,
    label: match.name,
    source: "search",
  };
}

export function isInSeattleArea(lat: number, lng: number): boolean {
  return isInMarketArea(lat, lng, "seattle");
}

export function distanceMiles(
  from: Pick<SearchOrigin, "lat" | "lng">,
  to: { lat: number; lng: number },
): number {
  const radians = (degrees: number) => (degrees * Math.PI) / 180;
  const earthRadiusMiles = 3958.8;
  const deltaLat = radians(to.lat - from.lat);
  const deltaLng = radians(to.lng - from.lng);
  const fromLat = radians(from.lat);
  const toLat = radians(to.lat);
  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(fromLat) * Math.cos(toLat) * Math.sin(deltaLng / 2) ** 2;
  return earthRadiusMiles * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function dealDistanceMiles(
  deal: Deal,
  origin: SearchOrigin | null,
): number | null {
  if (!origin || deal.lat == null || deal.lng == null) return null;
  return distanceMiles(origin, { lat: deal.lat, lng: deal.lng });
}

export function sortDealsByDistance(
  deals: Deal[],
  origin: SearchOrigin | null,
): Deal[] {
  if (!origin) return deals;
  return [...deals].sort((left, right) => {
    const leftDistance = dealDistanceMiles(left, origin);
    const rightDistance = dealDistanceMiles(right, origin);
    if (leftDistance == null && rightDistance == null) return 0;
    if (leftDistance == null) return 1;
    if (rightDistance == null) return -1;
    return leftDistance - rightDistance;
  });
}

type CensusPayload = {
  result?: {
    addressMatches?: Array<{
      matchedAddress?: string;
      coordinates?: { x?: number; y?: number };
    }>;
  };
};

export function parseCensusLocation(
  payload: CensusPayload,
  market: Market,
): SearchOrigin | null {
  const match = payload.result?.addressMatches?.[0];
  const lat = match?.coordinates?.y;
  const lng = match?.coordinates?.x;
  if (
    typeof lat !== "number" ||
    typeof lng !== "number" ||
    !Number.isFinite(lat) ||
    !Number.isFinite(lng) ||
    !isInMarketArea(lat, lng, market)
  ) {
    return null;
  }
  return {
    lat,
    lng,
    label: match?.matchedAddress || `Searched location in ${MARKETS[market].label}`,
    source: "search",
  };
}
