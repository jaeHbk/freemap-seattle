export type Market = "seattle" | "atlanta";

export interface MarketConfig {
  id: Market;
  label: string;
  regionLabel: string;
  addressSuffix: string;
  center: readonly [lat: number, lng: number];
  zoom: number;
  bounds: {
    minLat: number;
    maxLat: number;
    minLng: number;
    maxLng: number;
  };
}

export const DEFAULT_MARKET: Market = "seattle";

export const MARKETS: Record<Market, MarketConfig> = {
  seattle: {
    id: "seattle",
    label: "Seattle",
    regionLabel: "Seattle, WA",
    addressSuffix: "Seattle, WA",
    center: [47.6062, -122.3321],
    zoom: 12,
    bounds: {
      minLat: 47.45,
      maxLat: 47.75,
      minLng: -122.46,
      maxLng: -122.2,
    },
  },
  atlanta: {
    id: "atlanta",
    label: "Atlanta",
    regionLabel: "Atlanta, GA",
    addressSuffix: "Atlanta, GA",
    center: [33.749, -84.388],
    zoom: 11.5,
    bounds: {
      minLat: 33.55,
      maxLat: 34.05,
      minLng: -84.62,
      maxLng: -84.15,
    },
  },
};

export const MARKET_OPTIONS = Object.values(MARKETS);

export function parseMarket(value: string | null | undefined): Market {
  return value === "atlanta" || value === "seattle"
    ? value
    : DEFAULT_MARKET;
}

export function isInMarketArea(
  lat: number,
  lng: number,
  market: Market,
): boolean {
  const bounds = MARKETS[market].bounds;
  return (
    lat >= bounds.minLat &&
    lat <= bounds.maxLat &&
    lng >= bounds.minLng &&
    lng <= bounds.maxLng
  );
}
