"use client";

import { Drawer } from "@base-ui/react/drawer";
import {
  BellRing,
  MapPin,
  RefreshCw,
  X,
} from "lucide-react";

import { Toggle } from "@/components/ui/switch";
import {
  MAX_ALERT_RADIUS_MILES,
  MIN_ALERT_RADIUS_MILES,
} from "@/lib/deal-preferences";
import type { SearchOrigin } from "@/lib/location";
import { cn } from "@/lib/utils";

export type AlertPermission =
  | "default"
  | "granted"
  | "denied"
  | "unsupported";

interface DealAlertsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  enabled: boolean;
  radiusMiles: number;
  origin: SearchOrigin | null;
  permission: AlertPermission;
  pending: boolean;
  error: string | null;
  onEnabledChange: (enabled: boolean) => void;
  onRadiusChange: (radiusMiles: number) => void;
  onCheckNow: () => void;
}

export function DealAlerts({
  open,
  onOpenChange,
  enabled,
  radiusMiles,
  origin,
  permission,
  pending,
  error,
  onEnabledChange,
  onRadiusChange,
  onCheckNow,
}: DealAlertsProps) {
  return (
    <Drawer.Root
      open={open}
      onOpenChange={onOpenChange}
      swipeDirection="right"
    >
      <Drawer.Portal>
        <Drawer.Backdrop className="fixed inset-0 z-[900] bg-black/40 backdrop-blur-sm transition-opacity data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 motion-reduce:transition-none" />
        <Drawer.Viewport className="pointer-events-none fixed inset-0 z-[1000]">
          <Drawer.Popup
            className={cn(
              "pointer-events-auto fixed inset-y-0 right-0 flex w-[min(24rem,100vw)] flex-col border-l border-border bg-background shadow-2xl",
              "transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] data-[ending-style]:translate-x-full data-[starting-style]:translate-x-full motion-reduce:transition-none",
            )}
          >
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <Drawer.Title className="flex items-center gap-2 font-heading text-lg font-semibold text-foreground">
                <BellRing className="size-5 text-primary" />
                Deal alerts
              </Drawer.Title>
              <Drawer.Close
                className="flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close deal alerts"
              >
                <X className="size-4" />
              </Drawer.Close>
            </div>

            <div className="flex flex-1 flex-col gap-7 overflow-y-auto px-6 py-6">
              <Toggle
                id="nearby-deal-alerts"
                label="Nearby deal alerts"
                checked={enabled}
                disabled={pending}
                onCheckedChange={onEnabledChange}
              />

              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-4">
                  <label
                    htmlFor="alert-radius"
                    className="text-sm font-medium text-foreground"
                  >
                    Alert radius
                  </label>
                  <output
                    htmlFor="alert-radius"
                    className="text-sm font-semibold tabular-nums text-primary"
                  >
                    {radiusMiles} mi
                  </output>
                </div>
                <input
                  id="alert-radius"
                  type="range"
                  min={MIN_ALERT_RADIUS_MILES}
                  max={MAX_ALERT_RADIUS_MILES}
                  step={1}
                  value={radiusMiles}
                  disabled={pending}
                  onChange={(event) =>
                    onRadiusChange(Number(event.currentTarget.value))
                  }
                  className="h-2 w-full cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-60"
                />
              </div>

              <div
                className="flex items-start gap-3 border-t border-border pt-5 text-sm"
                role="status"
              >
                <MapPin className="mt-0.5 size-4 shrink-0 text-primary" />
                <span className="text-muted-foreground">
                  {origin ? origin.label : "Choose a Seattle location"}
                </span>
              </div>

              {permission === "denied" && (
                <p className="text-sm text-destructive">
                  Browser notifications are blocked for this site.
                </p>
              )}
              {permission === "unsupported" && (
                <p className="text-sm text-destructive">
                  Browser notifications are unavailable.
                </p>
              )}
              {error && (
                <p className="text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}
            </div>

            <div className="border-t border-border p-4">
              <button
                type="button"
                onClick={onCheckNow}
                disabled={!enabled || pending}
                className={cn(
                  "inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-border px-4 text-sm font-semibold",
                  enabled && !pending
                    ? "text-foreground hover:bg-accent"
                    : "cursor-not-allowed text-muted-foreground/50",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                <RefreshCw
                  className={cn("size-4", pending && "animate-spin")}
                />
                Check now
              </button>
            </div>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
