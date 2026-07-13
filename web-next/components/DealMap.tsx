"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { Loader2, MapPinOff } from "lucide-react";
import type { Deal } from "@/components/deals";
import { TYPE_STYLE } from "@/components/deal-style";

// Leaflet needs `window`, so the map is loaded client-only (no SSR).
const DealMapInner = dynamic(() => import("@/components/DealMap.inner"), {
  ssr: false,
  loading: () => (
    <div className="flex size-full items-center justify-center bg-[var(--map-bg)] text-muted-foreground">
      <Loader2 className="size-6 animate-spin motion-reduce:animate-none" />
      <span className="sr-only">Loading map</span>
    </div>
  ),
});

function LegendGlyph({ shape, color }: { shape: string; color: string }) {
  if (shape === "square")
    return <span className="size-3 rounded-[2px]" style={{ background: color }} aria-hidden />;
  if (shape === "diamond")
    return <span className="size-3 rotate-45 rounded-[1px]" style={{ background: color }} aria-hidden />;
  return <span className="size-3 rounded-full" style={{ background: color }} aria-hidden />;
}

interface DealMapProps {
  deals: Deal[];
  onClearFilters?: () => void;
}

export function DealMap({ deals, onClearFilters }: DealMapProps) {
  return (
    <div className="relative size-full overflow-hidden rounded-2xl border border-border shadow-sm">
      <DealMapInner deals={deals} />
      {deals.length === 0 && (
        <div
          role="status"
          className="absolute left-1/2 top-4 z-[500] flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-3 rounded-lg border border-border bg-card/95 px-4 py-3 shadow-lg backdrop-blur-sm"
        >
          <MapPinOff className="size-5 shrink-0 text-muted-foreground" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">No mapped deals</p>
            <p className="text-xs text-muted-foreground">
              {onClearFilters
                ? "Nothing matches these filters."
                : "No geocoded deals are available right now."}
            </p>
          </div>
          {onClearFilters && (
            <button
              type="button"
              onClick={onClearFilters}
              className="shrink-0 rounded-md text-xs font-semibold text-primary hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Clear filters
            </button>
          )}
        </div>
      )}
      <div
        className="pointer-events-none absolute bottom-4 left-4 z-[500] rounded-xl border border-border/80 bg-card/90 px-3 py-2.5 text-xs shadow-lg backdrop-blur-sm"
        aria-hidden
      >
        <p className="mb-1.5 font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          Deal type
        </p>
        <ul className="flex flex-col gap-1">
          {(["free", "bogo", "other"] as const).map((t) => (
            <li key={t} className="flex items-center gap-2 font-medium text-foreground">
              <LegendGlyph shape={TYPE_STYLE[t].shape} color={TYPE_STYLE[t].color} />
              {TYPE_STYLE[t].label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
