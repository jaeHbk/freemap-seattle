"use client";

import * as React from "react";
import {
  Badge,
  Button,
  Heading,
  IconButton,
  Item,
  StatusDot,
  Text,
} from "@astryxdesign/core";
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
  Heart,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { safeHttpUrl } from "@/components/deals";
import type { Deal } from "@/components/deals";
import { TYPE_STYLE, STATUS_LABEL } from "@/components/deal-style";
import {
  dealDistanceMiles,
  type SearchOrigin,
} from "@/lib/location";
import { dealPreferenceKey } from "@/lib/deal-preferences";

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

function ShapeGlyph({ shape }: { shape: string }) {
  const base = "inline-block size-2.5 shrink-0";
  if (shape === "square")
    return <span className={cn(base, "rounded-[2px] bg-current")} aria-hidden />;
  if (shape === "diamond")
    return (
      <span
        className={cn(base, "rotate-45 rounded-[1px] bg-current")}
        aria-hidden
      />
    );
  return <span className={cn(base, "rounded-full bg-current")} aria-hidden />;
}

const TYPE_BADGE_VARIANT = {
  free: "green",
  bogo: "blue",
  other: "orange",
} as const;

function evidenceSummary(deal: Deal): string {
  const source =
    deal.verification_status === "official"
      ? "Official source"
      : deal.verification_status === "corroborated"
        ? "Corroborated"
        : "Source reported";
  if (!deal.evidence_count) return source;
  return `${source} · ${deal.evidence_count} ${
    deal.evidence_count === 1 ? "source" : "sources"
  }`;
}

interface DealCardProps {
  deal: Deal;
  index: number;
  reduce: boolean | null;
  origin: SearchOrigin | null;
  selected: boolean;
  favorite: boolean;
  onSelectDeal: (dealId: string) => void;
  onToggleFavorite: (deal: Deal) => void;
  onShowOnMap: (dealId: string) => void;
  onViewDetails: (dealId: string) => void;
}

function DealCard({
  deal,
  index,
  reduce,
  origin,
  selected,
  favorite,
  onSelectDeal,
  onToggleFavorite,
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
      className={cn(
        "transition-colors",
        selected && "bg-accent/50",
      )}
      onFocusCapture={() => onSelectDeal(dealId)}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.03, 0.3), ease: [0.22, 1, 0.36, 1] }}
    >
      <Item
        as="div"
        density="spacious"
        align="start"
        className={cn(
          "max-sm:flex-col max-sm:items-stretch",
          stale && "opacity-65",
        )}
        startContent={
          <Badge
            variant={TYPE_BADGE_VARIANT[deal.deal_type] ?? "orange"}
            icon={<ShapeGlyph shape={ts.shape} />}
            label={ts.label}
          />
        }
        label={
          <div className="min-w-0">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <Text type="supporting" className="capitalize">
                {deal.category}
              </Text>
              {stale ? (
                <Badge variant="warning" icon={<Clock />} label={STATUS_LABEL[deal.status]} />
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  <StatusDot variant="success" label="Active deal" />
                  <Text type="supporting">{STATUS_LABEL[deal.status]}</Text>
                </span>
              )}
            </div>
            <Heading level={3} maxLines={2}>
              {deal.title}
            </Heading>
          </div>
        }
        description={
          <div className="mt-2 flex min-w-0 flex-col gap-2">
            {deal.description && (
              <Text type="supporting" maxLines={2}>
                {deal.description}
              </Text>
            )}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground">
              <span className="inline-flex min-w-0 items-center gap-1.5">
                {location.icon}
                <Text type="supporting" color="primary">
                  {location.label}
                </Text>
                {distance != null && (
                  <Text type="supporting" hasTabularNumbers>
                    · {distance < 0.1 ? "<0.1" : distance.toFixed(1)} mi
                  </Text>
                )}
              </span>
              <Text type="supporting">{evidenceSummary(deal)}</Text>
            </div>
            {location.detail && (
              <Text type="supporting" maxLines={1}>
                {location.detail}
              </Text>
            )}
          </div>
        }
        endContent={
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1 max-sm:w-full max-sm:justify-start">
            <IconButton
              label={`${favorite ? "Remove" : "Add"} ${deal.title} ${
                favorite ? "from" : "to"
              } favorites`}
              tooltip={favorite ? "Remove from favorites" : "Add to favorites"}
              icon={<Heart fill={favorite ? "currentColor" : "none"} />}
              variant={favorite ? "primary" : "ghost"}
              size="sm"
              aria-pressed={favorite}
              onClick={() => onToggleFavorite(deal)}
            />
            <Button
              label="Details"
              icon={<Info />}
              variant="ghost"
              size="sm"
              onClick={() => {
                onSelectDeal(dealId);
                onViewDetails(dealId);
              }}
            />
            {mapped && (
              <Button
                label="Show on map"
                icon={<Map />}
                variant="ghost"
                size="sm"
                onClick={() => onShowOnMap(dealId)}
              />
            )}
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold text-primary hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                View deal
                <ExternalLink className="size-3.5" />
              </a>
            ) : (
              <Text type="supporting" color="disabled">
                Link unavailable
              </Text>
            )}
          </div>
        }
      />
    </motion.li>
  );
}

interface DealListProps {
  deals: Deal[];
  origin: SearchOrigin | null;
  selectedDealId: string | null;
  favoriteDealKeys: ReadonlySet<string>;
  onSelectDeal: (dealId: string) => void;
  onToggleFavorite: (deal: Deal) => void;
  onShowOnMap: (dealId: string) => void;
  onViewDetails: (dealId: string) => void;
  onClearFilters: () => void;
}

export function DealList({
  deals,
  origin,
  selectedDealId,
  favoriteDealKeys,
  onSelectDeal,
  onToggleFavorite,
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
      className="divide-y divide-border border-y border-border bg-card"
    >
      {deals.map((d, i) => (
        <DealCard
          key={d.id}
          deal={d}
          index={i}
          reduce={reduce}
          origin={origin}
          selected={String(d.id) === selectedDealId}
          favorite={favoriteDealKeys.has(dealPreferenceKey(d))}
          onSelectDeal={onSelectDeal}
          onToggleFavorite={onToggleFavorite}
          onShowOnMap={onShowOnMap}
          onViewDetails={onViewDetails}
        />
      ))}
    </ul>
  );
}
