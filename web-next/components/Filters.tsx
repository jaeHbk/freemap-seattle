"use client";

import * as React from "react";
import {
  Button,
  Divider,
  Switch,
  Text,
  VStack,
} from "@astryxdesign/core";
import { RotateCcw } from "lucide-react";
import type { FilterState, DealType, Category, Placement } from "@/components/deals";
import { EMPTY_FILTERS } from "@/components/deals";
import { FieldSelect } from "@/components/ui/select";

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
  idPrefix: string;
  /** number of deals currently visible (for the live count line) */
  count?: number;
}

export function Filters({ state, onChange, idPrefix, count }: FiltersProps) {
  const set = <K extends keyof FilterState>(key: K, value: FilterState[K]) =>
    onChange({ ...state, [key]: value });

  const dirty =
    state.type !== "" ||
    state.category !== "" ||
    state.placement !== "" ||
    state.includeStale;

  return (
    <VStack gap={4}>
      <FieldSelect
        id={`${idPrefix}-filter-type`}
        label="Deal type"
        value={state.type}
        onValueChange={(v) => set("type", v as "" | DealType)}
        options={TYPE_OPTS}
      />
      <FieldSelect
        id={`${idPrefix}-filter-category`}
        label="Category"
        value={state.category}
        onValueChange={(v) => set("category", v as "" | Category)}
        options={CATEGORY_OPTS}
      />
      <FieldSelect
        id={`${idPrefix}-filter-placement`}
        label="Where"
        value={state.placement}
        onValueChange={(v) => set("placement", v as "" | Placement)}
        options={PLACEMENT_OPTS}
      />

      <Divider />

      <Switch
        id={`${idPrefix}-filter-stale`}
        label="Show stale deals"
        description="Include offers that may no longer be available"
        value={state.includeStale}
        onChange={(checked) => set("includeStale", checked)}
        labelSpacing="spread"
        labelPosition="start"
      />

      {typeof count === "number" && (
        <Text type="supporting" display="block" hasTabularNumbers>
          <Text type="inherit" color="primary" weight="semibold">
            {count}
          </Text>{" "}
          {count === 1 ? "deal" : "deals"} match
        </Text>
      )}

      <Button
        label="Clear filters"
        icon={<RotateCcw />}
        size="sm"
        width="100%"
        isDisabled={!dirty}
        onClick={() => onChange(EMPTY_FILTERS)}
      />
    </VStack>
  );
}
