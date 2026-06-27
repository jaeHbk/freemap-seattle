"use client";

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { ExternalLink, Globe, MapPin, SearchX, Clock } from "lucide-react";
import {
  TextureCard,
  TextureCardContent,
} from "@/components/ui/texture-card";
import { cn } from "@/lib/utils";
import { safeHttpUrl } from "@/components/deals";
import type { Deal } from "@/components/deals";
import { TYPE_STYLE, STATUS_LABEL } from "@/components/deal-style";

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

function DealCard({ deal, index, reduce }: { deal: Deal; index: number; reduce: boolean | null }) {
  const ts = TYPE_STYLE[deal.deal_type] ?? TYPE_STYLE.other;
  const stale = deal.status === "stale";
  const href = safeHttpUrl(deal.url);

  return (
    <motion.li
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.03, 0.3), ease: [0.22, 1, 0.36, 1] }}
    >
      <TextureCard className={cn("h-full transition-opacity", stale && "opacity-65")}>
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

          <div className="mt-auto flex items-center justify-between gap-3 pt-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              {deal.placement === "online" ? (
                <Globe className="size-3.5" />
              ) : (
                <MapPin className="size-3.5" />
              )}
              {deal.raw_location || (deal.placement === "online" ? "Online" : "In person")}
            </span>
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
          </div>
        </TextureCardContent>
      </TextureCard>
    </motion.li>
  );
}

interface DealListProps {
  deals: Deal[];
  onClearFilters: () => void;
}

export function DealList({ deals, onClearFilters }: DealListProps) {
  const reduce = useReducedMotion();

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
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {deals.map((d, i) => (
        <DealCard key={d.id} deal={d} index={i} reduce={reduce} />
      ))}
    </ul>
  );
}
