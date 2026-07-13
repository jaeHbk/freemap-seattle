// Visual encoding for deal_type — color AND shape, so color is never the sole
// signal (a11y). Shared by the list badges, map pins, and the legend.
import type { DealType, DealStatus } from "@/components/deals";

export interface TypeStyle {
  label: string;
  color: string; // hex, used for pin fill + badge accent
  shape: "circle" | "square" | "diamond"; // the non-color signal
}

export const TYPE_STYLE: Record<DealType, TypeStyle> = {
  free: { label: "Free", color: "#1f7a4d", shape: "circle" },
  bogo: { label: "BOGO", color: "#0e7490", shape: "square" },
  other: { label: "Other", color: "#b45309", shape: "diamond" },
};

export const STATUS_LABEL: Record<DealStatus, string> = {
  active: "Active",
  stale: "Stale",
  expired: "Expired",
};
