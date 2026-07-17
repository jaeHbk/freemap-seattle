import type { Deal } from "@/components/deals";
import {
  dealDistanceMiles,
  type SearchOrigin,
} from "./location.ts";

export const FAVORITES_STORAGE_KEY = "freemap:favorites:v1";
export const ALERTS_STORAGE_KEY = "freemap:alerts:v1";
export const MIN_ALERT_RADIUS_MILES = 1;
export const MAX_ALERT_RADIUS_MILES = 10;
const MAX_SEEN_DEALS = 500;

export interface AlertPreferences {
  enabled: boolean;
  radiusMiles: number;
  seenDealKeys: string[];
}

export const DEFAULT_ALERT_PREFERENCES: AlertPreferences = {
  enabled: false,
  radiusMiles: 3,
  seenDealKeys: [],
};

export function dealPreferenceKey(
  deal: Pick<Deal, "id" | "source" | "source_id">,
): string {
  return `${deal.source}:${deal.source_id || String(deal.id)}`;
}

export function parseFavoriteKeys(value: string | null): Set<string> {
  if (!value) return new Set();
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter(
        (item): item is string =>
          typeof item === "string" && item.length > 0,
      ),
    );
  } catch {
    return new Set();
  }
}

export function serializeFavoriteKeys(keys: ReadonlySet<string>): string {
  return JSON.stringify([...keys].sort());
}

export function parseAlertPreferences(value: string | null): AlertPreferences {
  if (!value) return DEFAULT_ALERT_PREFERENCES;
  try {
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object") {
      return DEFAULT_ALERT_PREFERENCES;
    }
    const candidate = parsed as Partial<AlertPreferences>;
    const radius =
      typeof candidate.radiusMiles === "number" &&
      Number.isFinite(candidate.radiusMiles)
        ? Math.min(
            MAX_ALERT_RADIUS_MILES,
            Math.max(MIN_ALERT_RADIUS_MILES, candidate.radiusMiles),
          )
        : DEFAULT_ALERT_PREFERENCES.radiusMiles;
    const seen = Array.isArray(candidate.seenDealKeys)
      ? candidate.seenDealKeys.filter(
          (item): item is string =>
            typeof item === "string" && item.length > 0,
        )
      : [];
    return {
      enabled: candidate.enabled === true,
      radiusMiles: radius,
      seenDealKeys: [...new Set(seen)].slice(-MAX_SEEN_DEALS),
    };
  } catch {
    return DEFAULT_ALERT_PREFERENCES;
  }
}

export function serializeAlertPreferences(
  preferences: AlertPreferences,
): string {
  return JSON.stringify(preferences);
}

export function mergeSeenDealKeys(
  previous: readonly string[],
  deals: readonly Deal[],
): string[] {
  const keys = new Set(previous);
  for (const deal of deals) keys.add(dealPreferenceKey(deal));
  return [...keys].slice(-MAX_SEEN_DEALS);
}

export function unseenNearbyDeals(
  deals: readonly Deal[],
  seenDealKeys: readonly string[],
  origin: SearchOrigin | null,
  radiusMiles: number,
): Deal[] {
  if (!origin) return [];
  const seen = new Set(seenDealKeys);
  return deals.filter((deal) => {
    if (deal.status !== "active" || seen.has(dealPreferenceKey(deal))) {
      return false;
    }
    const distance = dealDistanceMiles(deal, origin);
    return distance !== null && distance <= radiusMiles;
  });
}
