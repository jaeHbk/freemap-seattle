"use client";

import * as React from "react";
import { Tabs as BaseTabs } from "@base-ui/react/tabs";
import { Map as MapIcon, List as ListIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type ViewValue = "map" | "list";

// Stable ARIA ids shared between the tabs (here) and the panels (in page.tsx),
// so each tab's aria-controls points at its real panel and each panel's
// aria-labelledby points back. Kept in one place so the contract can't drift.
export const TAB_IDS: Record<ViewValue, string> = { map: "tab-map", list: "tab-list" };
export const PANEL_IDS: Record<ViewValue, string> = { map: "panel-map", list: "panel-list" };

interface ViewTabsProps {
  value: ViewValue;
  onValueChange: (v: ViewValue) => void;
  mapCount: number;
  listCount: number;
}

// Real ARIA tabs: base-ui gives the tablist + roving focus + arrow-key nav; we
// add aria-controls -> panel id and an id on each tab so the panel can label
// back. aria-selected is driven by `value`. Rendered exactly once on the page so
// the a11y tree holds a single tablist.
export function ViewTabs({ value, onValueChange, mapCount, listCount }: ViewTabsProps) {
  return (
    <BaseTabs.Root value={value} onValueChange={(v) => onValueChange(v as ViewValue)}>
      <BaseTabs.List
        className="relative inline-flex items-center gap-1 rounded-full border border-border bg-card/70 p-1 shadow-sm"
        aria-label="Choose how to view deals"
      >
        <Tab value="map" icon={<MapIcon className="size-4" />} label="Map" count={mapCount} />
        <Tab value="list" icon={<ListIcon className="size-4" />} label="List" count={listCount} />
        <BaseTabs.Indicator
          className={cn(
            "absolute left-0 top-1 z-0 h-[calc(100%-0.5rem)] w-[var(--active-tab-width)] translate-x-[var(--active-tab-left)] rounded-full bg-primary",
            "transition-[transform,width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none"
          )}
        />
      </BaseTabs.List>
    </BaseTabs.Root>
  );
}

function Tab({
  value,
  icon,
  label,
  count,
}: {
  value: ViewValue;
  icon: React.ReactNode;
  label: string;
  count: number;
}) {
  return (
    <BaseTabs.Tab
      value={value}
      id={TAB_IDS[value]}
      aria-controls={PANEL_IDS[value]}
      className={cn(
        "group/tab relative z-10 inline-flex select-none items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold transition-colors sm:px-4",
        "text-muted-foreground data-[selected]:text-primary-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      )}
    >
      {icon}
      {label}
      <span className="rounded-full bg-foreground/10 px-1.5 text-xs tabular-nums group-data-[selected]/tab:bg-white/20">
        {count}
      </span>
    </BaseTabs.Tab>
  );
}
