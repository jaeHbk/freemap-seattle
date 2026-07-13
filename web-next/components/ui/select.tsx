"use client";

import * as React from "react";
import { Select as BaseSelect } from "@base-ui/react/select";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SelectOption {
  label: string;
  value: string;
}

interface FieldSelectProps {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  icon?: React.ReactNode;
  id?: string;
}

// A labelled select built on @base-ui select primitives. Keyboard + ARIA come
// from base-ui; styling is ours. Values are plain strings ("" = "All").
export function FieldSelect({
  label,
  value,
  onValueChange,
  options,
  icon,
  id,
}: FieldSelectProps) {
  const current = options.find((o) => o.value === value);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        {icon}
        {label}
      </span>
      <BaseSelect.Root
        items={options}
        value={value}
        onValueChange={(v) => onValueChange((v as string) ?? "")}
      >
        <BaseSelect.Trigger
          id={id}
          aria-label={label}
          className={cn(
            "group flex h-10 w-full items-center justify-between gap-2 rounded-xl border border-border bg-card/80 px-3.5 text-sm font-medium text-foreground shadow-sm",
            "transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
            "data-[popup-open]:border-primary/60"
          )}
        >
          <BaseSelect.Value>{current?.label ?? "All"}</BaseSelect.Value>
          <BaseSelect.Icon className="text-muted-foreground transition-transform group-data-[popup-open]:rotate-180 motion-reduce:transition-none">
            <ChevronsUpDown className="size-4" />
          </BaseSelect.Icon>
        </BaseSelect.Trigger>
        <BaseSelect.Portal>
          <BaseSelect.Positioner sideOffset={6} className="z-[1100]">
            <BaseSelect.Popup
              className={cn(
                "max-h-[min(20rem,var(--available-height))] min-w-[var(--anchor-width)] origin-[var(--transform-origin)] overflow-y-auto rounded-xl border border-border bg-popover p-1 text-popover-foreground shadow-xl",
                "transition-[transform,opacity] data-[starting-style]:scale-95 data-[starting-style]:opacity-0 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 motion-reduce:transition-none"
              )}
            >
              {options.map((opt) => (
                <BaseSelect.Item
                  key={opt.value || "all"}
                  value={opt.value}
                  className={cn(
                    "flex cursor-default select-none items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm outline-none",
                    "data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"
                  )}
                >
                  <BaseSelect.ItemText>{opt.label}</BaseSelect.ItemText>
                  <BaseSelect.ItemIndicator>
                    <Check className="size-4 text-primary" />
                  </BaseSelect.ItemIndicator>
                </BaseSelect.Item>
              ))}
            </BaseSelect.Popup>
          </BaseSelect.Positioner>
        </BaseSelect.Portal>
      </BaseSelect.Root>
    </div>
  );
}
