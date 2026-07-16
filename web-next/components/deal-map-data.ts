import type { Deal, DealStatus, DealType } from "@/components/deals";

export const OPENFREEMAP_STYLE_URL =
  "https://tiles.openfreemap.org/styles/liberty";

export interface DealMapProperties {
  dealId: string;
  dealType: DealType;
  status: DealStatus;
  title: string;
}

export interface DealMapFeature {
  type: "Feature";
  id: string;
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
  properties: DealMapProperties;
}

export interface DealMapFeatureCollection {
  type: "FeatureCollection";
  features: DealMapFeature[];
}

export function dealsToFeatureCollection(
  deals: Deal[],
): DealMapFeatureCollection {
  return {
    type: "FeatureCollection",
    features: deals.flatMap((deal) => {
      if (deal.lat == null || deal.lng == null) return [];

      const dealId = String(deal.id);
      return [
        {
          type: "Feature" as const,
          id: dealId,
          geometry: {
            type: "Point" as const,
            coordinates: [deal.lng, deal.lat] as [number, number],
          },
          properties: {
            dealId,
            dealType: deal.deal_type,
            status: deal.status,
            title: deal.title,
          },
        },
      ];
    }),
  };
}
