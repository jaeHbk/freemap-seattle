"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  Clock,
  ExternalLink,
  Globe,
  Info,
  Map,
  MapPinned,
  MapPinOff,
  SearchX,
} from "lucide-react";
import {
  TextureCard,
  TextureCardContent,
} from "@/components/ui/texture-card";
import { cn } from "@/lib/utils";
import { safeHttpUrl } from "@/components/deals";
import type { Deal } from "@/components/deals";
import { TYPE_STYLE, STATUS_LABEL } from "@/components/deal-style";
import {
  dealDistanceMiles,
  type SearchOrigin,
} from "@/lib/location";

function locationPresentation(deal: Deal) {
  if (deal.placement === "online") {
    return {
      icon: <Globe className="size-3.5" />,
      label: "Online",
      detail: deal.raw_location,
    };
  }
  if (
    deal.geocode_status === "ok" &&
    deal.lat != null &&
    deal.lng != null
  ) {
    return {
      icon: <MapPinned className="size-3.5" />,
      label: "On map",
      detail: deal.raw_location,
    };
  }
  return {
    icon: <MapPinOff className="size-3.5" />,
    label: "Map location unavailable",
    detail: deal.raw_location,
  };
}

function ShapeGlyph({ shape, color }: { shape: string; color: string }) {
  const base = "inline-block size-2.5 shrink-0";
  if (shape === "square")
    return <span className={cn(base, "rounded-[2px]")} style={{ background: color }} aria-hidden />;
  if (shape === "diamond")
    return (
      <span
        className={cn(base, "rotate-45 rounded-[1px]")}
        style={{ background: color }}
        aria-hidden
      />
    );
  return <span className={cn(base, "rounded-full")} style={{ background: color }} aria-hidden />;
}

interface DealCardProps {
  deal: Deal;
  index: number;
  reduce: boolean | null;
  origin: SearchOrigin | null;
  selected: boolean;
  onSelectDeal: (dealId: string) => void;
  onShowOnMap: (dealId: string) => void;
  onViewDetails: (dealId: string) => void;
}

function DealCard({
  deal,
  index,
  reduce,
  origin,
  selected,
  onSelectDeal,
  onShowOnMap,
  onViewDetails,
}: DealCardProps) {
  const ts = TYPE_STYLE[deal.deal_type] ?? TYPE_STYLE.other;
  const stale = deal.status === "stale";
  const href = safeHttpUrl(deal.url);
  const location = locationPresentation(deal);
  const distance = dealDistanceMiles(deal, origin);
  const dealId = String(deal.id);
  const mapped = deal.lat != null && deal.lng != null;

  return (
    <motion.li
      data-deal-id={dealId}
      aria-current={selected ? "true" : undefined}
      onFocusCapture={() => onSelectDeal(dealId)}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.03, 0.3), ease: [0.22, 1, 0.36, 1] }}
    >
      <TextureCard
        className={cn(
          "h-full transition-[opacity,box-shadow,border-color]",
          stale && "opacity-65",
          selected && "border-primary/60 ring-2 ring-primary/20",
        )}
      >
        <TextureCardContent className="flex h-full flex-col gap-3 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold"
              style={{ background: `${ts.color}1a`, color: ts.color }}
            >
              <ShapeGlyph shape={ts.shape} color={ts.color} />
              {ts.label}
            </span>
            <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium capitalize text-muted-foreground">
              {deal.category}
            </span>
            <span
              className={cn(
                "ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.7rem] font-medium",
                stale
                  ? "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                  : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
              )}
            >
              {stale && <Clock className="size-3" />}
              {STATUS_LABEL[deal.status]}
            </span>
          </div>

          <h3 className="font-heading text-lg font-semibold leading-snug text-foreground">
            {deal.title}
          </h3>

          {deal.description && (
            <p className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">
              {deal.description}
            </p>
          )}

          <div className="mt-auto flex items-end justify-between gap-3 pt-1 text-xs text-muted-foreground">
            <span className="flex min-w-0 flex-col gap-1">
              <span className="inline-flex items-center gap-1.5 font-medium text-foreground/75">
                {location.icon}
                {location.label}
                {distance != null && (
                  <span className="tabular-nums text-muted-foreground">
                    · {distance < 0.1 ? "<0.1" : distance.toFixed(1)} mi
                  </span>
                )}
              </span>
              {location.detail && (
                <span className="line-clamp-2 leading-snug">
                  {location.detail}
                </span>
              )}
            </span>
            <span className="flex shrink-0 flex-col items-end gap-2">
              <button
                type="button"
                onClick={() => {
                  onSelectDeal(dealId);
                  onViewDetails(dealId);
                }}
                className="inline-flex items-center gap-1 rounded-md font-semibold text-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Info className="size-3.5" />
                Details
              </button>
              {mapped && (
                <button
                  type="button"
                  onClick={() => onShowOnMap(dealId)}
                  className="inline-flex items-center gap-1 rounded-md font-semibold text-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Map className="size-3.5" />
                  Show on map
                </button>
              )}
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cn(
                    "inline-flex items-center gap-1 rounded-md font-semibold text-primary transition-colors hover:text-primary/80",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                  )}
                >
                  View deal
                  <ExternalLink className="size-3.5" />
                </a>
              ) : (
                <span className="italic text-muted-foreground/70">link unavailable</span>
              )}
            </span>
          </div>
        </TextureCardContent>
      </TextureCard>
    </motion.li>
  );
}

interface DealListProps {
  deals: Deal[];
  origin: SearchOrigin | null;
  selectedDealId: string | null;
  onSelectDeal: (dealId: string) => void;
  onShowOnMap: (dealId: string) => void;
  onViewDetails: (dealId: string) => void;
  onClearFilters: () => void;
}

export function DealList({
  deals,
  origin,
  selectedDealId,
  onSelectDeal,
  onShowOnMap,
  onViewDetails,
  onClearFilters,
}: DealListProps) {
  const reduce = useReducedMotion();
  const listRef = React.useRef<HTMLUListElement>(null);

  React.useEffect(() => {
    if (!selectedDealId) return;
    const selected = Array.from(listRef.current?.children ?? []).find(
      (element) =>
        (element as HTMLElement).dataset.dealId === selectedDealId,
    );
    selected?.scrollIntoView({
      block: "nearest",
      behavior: reduce ? "auto" : "smooth",
    });
  }, [reduce, selectedDealId]);

  if (deals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <div className="flex size-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          <SearchX className="size-8" />
        </div>
        <div>
          <p className="font-heading text-lg font-semibold text-foreground">No matching deals</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Nothing fits these filters right now. Try widening your search.
          </p>
        </div>
        <button
          type="button"
          onClick={onClearFilters}
          className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          Clear filters
        </button>
      </div>
    );
  }

  return (
    <ul
      ref={listRef}
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
    >
      {deals.map((d, i) => (
        <DealCard
          key={d.id}
          deal={d}
          index={i}
          reduce={reduce}
          origin={origin}
          selected={String(d.id) === selectedDealId}
          onSelectDeal={onSelectDeal}
          onShowOnMap={onShowOnMap}
          onViewDetails={onViewDetails}
        />
      ))}
    </ul>
  );
}
