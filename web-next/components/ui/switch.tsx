"use client";

import * as React from "react";
import { Switch as BaseSwitch } from "@base-ui/react/switch";
import { cn } from "@/lib/utils";

interface ToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  id?: string;
}

// Labelled switch on @base-ui primitives. The whole row is a label so the hit
// target includes the text; the track respects prefers-reduced-motion.
export function Toggle({ checked, onCheckedChange, label, id }: ToggleProps) {
  return (
    <label
      htmlFor={id}
      className="flex cursor-pointer items-center justify-between gap-3 text-sm font-medium text-foreground"
    >
      {label}
      <BaseSwitch.Root
        id={id}
        checked={checked}
        onCheckedChange={(c) => onCheckedChange(c)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-border bg-muted transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "data-[checked]:border-primary data-[checked]:bg-primary motion-reduce:transition-none"
        )}
      >
        <BaseSwitch.Thumb
          className={cn(
            "size-5 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform",
            "data-[checked]:translate-x-[1.375rem] motion-reduce:transition-none"
          )}
        />
      </BaseSwitch.Root>
    </label>
  );
}
