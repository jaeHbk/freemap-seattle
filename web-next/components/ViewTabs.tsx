"use client";

import * as React from "react";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core";
import { Map as MapIcon, List as ListIcon } from "lucide-react";

export type ViewValue = "map" | "list";

// Stable ids keep each mode control connected to its rendered panel.
export const TAB_IDS: Record<ViewValue, string> = { map: "tab-map", list: "tab-list" };
export const PANEL_IDS: Record<ViewValue, string> = { map: "panel-map", list: "panel-list" };

interface ViewTabsProps {
  value: ViewValue;
  onValueChange: (v: ViewValue) => void;
  mapCount: number;
  listCount: number;
}

export function ViewTabs({ value, onValueChange, mapCount, listCount }: ViewTabsProps) {
  return (
    <>
      <SegmentedControl
        className="hidden sm:inline-flex"
        value={value}
        onChange={(next) => onValueChange(next as ViewValue)}
        label="Choose how to view deals"
        size="sm"
      >
        <SegmentedControlItem
          id={TAB_IDS.map}
          aria-controls={PANEL_IDS.map}
          value="map"
          icon={<MapIcon />}
          label={`Map ${mapCount}`}
        />
        <SegmentedControlItem
          id={TAB_IDS.list}
          aria-controls={PANEL_IDS.list}
          value="list"
          icon={<ListIcon />}
          label={`List ${listCount}`}
        />
      </SegmentedControl>
      <SegmentedControl
        className="inline-flex sm:hidden"
        value={value}
        onChange={(next) => onValueChange(next as ViewValue)}
        label="Choose how to view deals"
        size="sm"
      >
        <SegmentedControlItem
          value="map"
          icon={<MapIcon />}
          label={`Map, ${mapCount} deals`}
          isLabelHidden
        />
        <SegmentedControlItem
          value="list"
          icon={<ListIcon />}
          label={`List, ${listCount} deals`}
          isLabelHidden
        />
      </SegmentedControl>
    </>
  );
}
