"use client";

import * as React from "react";
import { Gift, Tag, Layers, MapPin, RotateCcw } from "lucide-react";
import { FieldSelect } from "@/components/ui/select";
import { Toggle } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { FilterState, DealType, Category, Placement } from "@/components/deals";
import { EMPTY_FILTERS } from "@/components/deals";

const TYPE_OPTS = [
  { label: "All deals", value: "" },
  { label: "Free", value: "free" },
  { label: "BOGO", value: "bogo" },
  { label: "Other", value: "other" },
];
const CATEGORY_OPTS = [
  { label: "All categories", value: "" },
  { label: "Food", value: "food" },
  { label: "Retail", value: "retail" },
  { label: "Event", value: "event" },
  { label: "Other", value: "other" },
];
// The placement control the old app left dead — now wired.
const PLACEMENT_OPTS = [
  { label: "Anywhere", value: "" },
  { label: "In person", value: "physical" },
  { label: "Online", value: "online" },
];

interface FiltersProps {
  state: FilterState;
  onChange: (next: FilterState) => void;
  /** number of deals currently visible (for the live count line) */
  count?: number;
}

export function Filters({ state, onChange, count }: FiltersProps) {
  const set = <K extends keyof FilterState>(key: K, value: FilterState[K]) =>
    onChange({ ...state, [key]: value });

  const dirty =
    state.type !== "" ||
    state.category !== "" ||
    state.placement !== "" ||
    state.includeStale;

  return (
    <div className="flex flex-col gap-6">
      <FieldSelect
        id="filter-type"
        label="Deal type"
        icon={<Gift className="size-3.5" />}
        value={state.type}
        onValueChange={(v) => set("type", v as "" | DealType)}
        options={TYPE_OPTS}
      />
      <FieldSelect
        id="filter-category"
        label="Category"
        icon={<Tag className="size-3.5" />}
        value={state.category}
        onValueChange={(v) => set("category", v as "" | Category)}
        options={CATEGORY_OPTS}
      />
      <FieldSelect
        id="filter-placement"
        label="Where"
        icon={<MapPin className="size-3.5" />}
        value={state.placement}
        onValueChange={(v) => set("placement", v as "" | Placement)}
        options={PLACEMENT_OPTS}
      />

      <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />

      <div className="flex flex-col gap-1.5">
        <span className="flex items-center gap-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          <Layers className="size-3.5" />
          Freshness
        </span>
        <Toggle
          id="filter-stale"
          label="Show stale deals"
          checked={state.includeStale}
          onCheckedChange={(c) => set("includeStale", c)}
        />
      </div>

      {typeof count === "number" && (
        <p className="text-sm text-muted-foreground">
          <span className="font-semibold text-foreground tabular-nums">{count}</span>{" "}
          {count === 1 ? "deal" : "deals"} match
        </p>
      )}

      <button
        type="button"
        disabled={!dirty}
        onClick={() => onChange(EMPTY_FILTERS)}
        className={cn(
          "flex items-center justify-center gap-2 rounded-xl border border-border px-3 py-2 text-sm font-medium transition-colors",
          dirty
            ? "text-foreground hover:border-primary/40 hover:bg-accent"
            : "cursor-not-allowed text-muted-foreground/50",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        )}
      >
        <RotateCcw className="size-3.5" />
        Clear filters
      </button>
    </div>
  );
}
