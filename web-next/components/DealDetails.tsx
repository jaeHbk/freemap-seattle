"use client";

import * as React from "react";
import { Drawer } from "@base-ui/react/drawer";
import {
  CalendarClock,
  Database,
  ExternalLink,
  MapPinned,
  ShieldCheck,
  TicketCheck,
  Users,
  X,
} from "lucide-react";

import { safeHttpUrl, type Deal } from "@/components/deals";
import { TYPE_STYLE, STATUS_LABEL } from "@/components/deal-style";
import { cn } from "@/lib/utils";

function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value.includes("T") ? value : value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(parsed);
}

function sourceLabel(source: string): string {
  if (source === "places_brand") return "Official brand terms";
  return source
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function DetailSection({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-border py-5">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <span className="text-primary">{icon}</span>
        {title}
      </h3>
      <div className="text-sm leading-relaxed text-muted-foreground">
        {children}
      </div>
    </section>
  );
}

interface DealDetailsProps {
  deal: Deal | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onShowOnMap: (dealId: string) => void;
}

export function DealDetails({
  deal,
  open,
  onOpenChange,
  onShowOnMap,
}: DealDetailsProps) {
  if (!deal) return null;

  const style = TYPE_STYLE[deal.deal_type] ?? TYPE_STYLE.other;
  const expires = formatDate(deal.expires_at);
  const verified = formatDate(deal.verified_at);
  const lastSeen = formatDate(deal.last_seen);
  const mapped = deal.lat != null && deal.lng != null;
  const links = [deal.url, ...(deal.alt_urls ?? [])]
    .map(safeHttpUrl)
    .filter((url): url is string => Boolean(url))
    .filter((url, index, values) => values.indexOf(url) === index);

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
              "pointer-events-auto fixed inset-y-0 right-0 flex w-[min(30rem,100vw)] flex-col border-l border-border bg-background shadow-2xl",
              "transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] data-[ending-style]:translate-x-full data-[starting-style]:translate-x-full motion-reduce:transition-none",
            )}
          >
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <p className="text-xs font-semibold uppercase text-muted-foreground">
              Deal details
            </p>
            <Drawer.Close
              className="flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close deal details"
            >
              <X className="size-4" />
            </Drawer.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-6 pb-8">
            <header className="py-6">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span
                  className="rounded-full px-2.5 py-1 text-xs font-semibold"
                  style={{ background: `${style.color}1a`, color: style.color }}
                >
                  {style.label}
                </span>
                <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium capitalize text-muted-foreground">
                  {deal.category}
                </span>
                <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                  {STATUS_LABEL[deal.status]}
                </span>
              </div>
              <Drawer.Title className="font-heading text-2xl font-semibold leading-tight text-foreground">
                {deal.title}
              </Drawer.Title>
              {deal.description && (
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {deal.description}
                </p>
              )}
              {deal.raw_location && (
                <p className="mt-4 flex items-start gap-2 text-sm text-foreground/80">
                  <MapPinned className="mt-0.5 size-4 shrink-0 text-primary" />
                  {deal.raw_location}
                </p>
              )}
            </header>

            <DetailSection
              icon={<Users className="size-4" />}
              title="Eligibility"
            >
              {deal.eligibility ?? "The source did not provide eligibility details."}
            </DetailSection>

            <DetailSection
              icon={<TicketCheck className="size-4" />}
              title="How to redeem"
            >
              {deal.redemption ?? "Open the source link for current redemption instructions."}
            </DetailSection>

            <DetailSection
              icon={<CalendarClock className="size-4" />}
              title="Timing"
            >
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
                <dt>Expires</dt>
                <dd className="text-right font-medium text-foreground">
                  {expires ?? "No fixed date supplied"}
                </dd>
                <dt>Verified</dt>
                <dd className="text-right font-medium text-foreground">
                  {verified ?? lastSeen ?? "Not supplied"}
                </dd>
              </dl>
            </DetailSection>

            <DetailSection
              icon={<Database className="size-4" />}
              title="Source"
            >
              <div className="flex items-center gap-2">
                <ShieldCheck className="size-4 text-primary" />
                <span>{sourceLabel(deal.source)}</span>
              </div>
            </DetailSection>

            <DetailSection
              icon={<ExternalLink className="size-4" />}
              title="Links"
            >
              {links.length > 0 ? (
                <ul className="flex flex-col gap-2">
                  {links.map((url, index) => (
                    <li key={url}>
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 font-semibold text-primary hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {index === 0 ? "Official deal page" : `Alternate source ${index}`}
                        <ExternalLink className="size-3.5" />
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                "No safe source link is available."
              )}
            </DetailSection>
          </div>

          {mapped && (
            <div className="border-t border-border bg-background p-4">
              <button
                type="button"
                onClick={() => {
                  onShowOnMap(String(deal.id));
                  onOpenChange(false);
                }}
                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <MapPinned className="size-4" />
                Show on map
              </button>
            </div>
          )}
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
