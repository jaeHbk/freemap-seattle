import type { Deal } from "@/components/deals";

export interface SearchOrigin {
  lat: number;
  lng: number;
  label: string;
  source: "search" | "geolocation";
}

interface Neighborhood {
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

const SEATTLE_BOUNDS = {
  minLat: 47.45,
  maxLat: 47.75,
  minLng: -122.46,
  maxLng: -122.2,
};

function normalizePlace(value: string): string {
  return value
    .toLowerCase()
    .replace(/\b(seattle|washington|wa|usa)\b/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function resolveNeighborhood(query: string): SearchOrigin | null {
  const normalized = normalizePlace(query);
  if (!normalized) return null;
  const match = SEATTLE_NEIGHBORHOODS.find((neighborhood) =>
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
  return (
    lat >= SEATTLE_BOUNDS.minLat &&
    lat <= SEATTLE_BOUNDS.maxLat &&
    lng >= SEATTLE_BOUNDS.minLng &&
    lng <= SEATTLE_BOUNDS.maxLng
  );
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

export function parseCensusLocation(payload: CensusPayload): SearchOrigin | null {
  const match = payload.result?.addressMatches?.[0];
  const lat = match?.coordinates?.y;
  const lng = match?.coordinates?.x;
  if (
    typeof lat !== "number" ||
    typeof lng !== "number" ||
    !Number.isFinite(lat) ||
    !Number.isFinite(lng) ||
    !isInSeattleArea(lat, lng)
  ) {
    return null;
  }
  return {
    lat,
    lng,
    label: match?.matchedAddress || "Searched location",
    source: "search",
  };
}
