"use client";

import * as React from "react";
import { Drawer } from "@base-ui/react/drawer";
import {
  MapPinned,
  SlidersHorizontal,
  X,
  Loader2,
  TriangleAlert,
  RefreshCw,
} from "lucide-react";

import Link from "next/link";

import { Filters } from "@/components/Filters";
import { DealList } from "@/components/DealList";
import { DealMap } from "@/components/DealMap";
import { ViewTabs, type ViewValue, TAB_IDS, PANEL_IDS } from "@/components/ViewTabs";
import {
  buildQuery,
  dealsForList,
  dealsForMap,
  EMPTY_FILTERS,
} from "@/components/deals";
import type { Deal, FilterState } from "@/components/deals";
import { cn } from "@/lib/utils";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready" };

interface MetaSource {
  last_successful_scrape?: string | null;
}

export default function Home() {
  const [filters, setFilters] = React.useState<FilterState>(EMPTY_FILTERS);
  const [view, setView] = React.useState<ViewValue>("map");
  const [deals, setDeals] = React.useState<Deal[]>([]);
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });
  const [freshness, setFreshness] = React.useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [reloadKey, setReloadKey] = React.useState(0);

  // Fetch deals whenever a SERVER-side filter changes. include_stale is the
  // server's source of truth (the old app's bug was refiltering only in memory);
  // type/category/placement are sent too so the payload stays small.
  React.useEffect(() => {
    const ctrl = new AbortController();
    // Synchronizing UI state with an external fetch is the intended use of an
    // effect; the loading flag is set once per request, not in a render loop.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ kind: "loading" });
    const qs = buildQuery(filters);
    fetch(`/api/deals${qs ? `?${qs}` : ""}`, { signal: ctrl.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`Server responded ${r.status}`);
        return r.json();
      })
      .then((data: Deal[]) => {
        setDeals(Array.isArray(data) ? data : []);
        setState({ kind: "ready" });
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "Could not load deals.",
        });
      });
    return () => ctrl.abort();
  }, [filters, reloadKey]);

  // Freshness badge — best-effort, never blocks the UI.
  React.useEffect(() => {
    const ctrl = new AbortController();
    fetch("/api/meta", { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((m: { sources?: MetaSource[] }) => {
        const latest = (m.sources ?? [])
          .map((s) => s.last_successful_scrape)
          .filter((x): x is string => Boolean(x))
          .sort()
          .at(-1);
        setFreshness(latest ?? null);
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, []);

  const mapDeals = React.useMemo(() => dealsForMap(deals, filters), [deals, filters]);
  const listDeals = React.useMemo(() => dealsForList(deals, filters), [deals, filters]);
  const visibleCount = view === "map" ? mapDeals.length : listDeals.length;

  const clearFilters = React.useCallback(() => setFilters(EMPTY_FILTERS), []);

  return (
    <div className="flex min-h-dvh flex-col">
      {/* Skip link — first focusable element, jumps keyboard users to content. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[1100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary-foreground"
      >
        Skip to deals
      </a>

      {/* Topbar */}
      <header className="sticky top-0 z-[600] border-b border-border bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-[1400px] items-center gap-4 px-4 py-3 sm:px-6">
          {/* The brand IS the page H1 — the document's top-level heading. */}
          <h1 className="m-0">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
                <MapPinned className="size-5" />
              </span>
              <span className="flex flex-col leading-none">
                <span className="font-heading text-xl font-semibold tracking-tight text-foreground">
                  FreeMap
                </span>
                <span className="text-[0.7rem] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  Seattle
                </span>
              </span>
              <span className="sr-only"> — free &amp; BOGO deals in Seattle</span>
            </Link>
          </h1>

          {/* Single source-of-truth tablist (one in the a11y tree at every
              viewport) — wraps under the brand on very narrow screens. */}
          <div className="ml-auto">
            <ViewTabs
              value={view}
              onValueChange={setView}
              mapCount={mapDeals.length}
              listCount={listDeals.length}
            />
          </div>

          <FreshnessBadge value={freshness} />

          {/* Mobile filter trigger */}
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-2 text-sm font-medium md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Open filters"
          >
            <SlidersHorizontal className="size-4" />
          </button>
        </div>

      </header>

      <div className="mx-auto flex w-full max-w-[1400px] flex-1 gap-6 px-4 py-6 sm:px-6">
        {/* Desktop sidebar. "Filters" is a control-group label, not document
            structure, so it's a plain styled label (no heading level under H1). */}
        <aside className="hidden w-64 shrink-0 md:block" aria-label="Filters">
          <div className="sticky top-24 rounded-2xl border border-border bg-card/60 p-5">
            <p className="mb-5 flex items-center gap-2 font-heading text-base font-semibold text-foreground">
              <SlidersHorizontal className="size-4 text-primary" />
              Filters
            </p>
            <Filters state={filters} onChange={setFilters} count={visibleCount} />
          </div>
        </aside>

        {/* Main panel. The active view is a real tabpanel: id + aria-labelledby
            back to its tab + tabIndex so keyboard users can land on it. */}
        <main id="main" className="flex min-w-0 flex-1 flex-col">
          {state.kind === "error" ? (
            <ErrorPanel message={state.message} onRetry={() => setReloadKey((k) => k + 1)} />
          ) : state.kind === "loading" ? (
            <LoadingPanel />
          ) : view === "map" ? (
            <section
              id={PANEL_IDS.map}
              role="tabpanel"
              aria-labelledby={TAB_IDS.map}
              tabIndex={0}
              className="h-[calc(100dvh-9rem)] min-h-[420px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <DealMap deals={mapDeals} />
            </section>
          ) : (
            <section
              id={PANEL_IDS.list}
              role="tabpanel"
              aria-labelledby={TAB_IDS.list}
              tabIndex={0}
              className="focus-visible:outline-none"
            >
              <DealList deals={listDeals} onClearFilters={clearFilters} />
            </section>
          )}
        </main>
      </div>

      {/* Mobile filter drawer */}
      <Drawer.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
        <Drawer.Portal>
          <Drawer.Backdrop className="fixed inset-0 z-[900] bg-black/40 backdrop-blur-sm transition-opacity data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 motion-reduce:transition-none" />
          <Drawer.Popup
            className={cn(
              "fixed inset-y-0 right-0 z-[1000] flex w-[min(20rem,90vw)] flex-col bg-background p-6 shadow-2xl",
              "transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] data-[ending-style]:translate-x-full data-[starting-style]:translate-x-full motion-reduce:transition-none"
            )}
          >
            <div className="mb-5 flex items-center justify-between">
              <Drawer.Title className="font-heading text-lg font-semibold text-foreground">
                Filters
              </Drawer.Title>
              <Drawer.Close
                className="flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close filters"
              >
                <X className="size-4" />
              </Drawer.Close>
            </div>
            <Filters state={filters} onChange={setFilters} count={visibleCount} />
          </Drawer.Popup>
        </Drawer.Portal>
      </Drawer.Root>
    </div>
  );
}

function FreshnessBadge({ value }: { value: string | null }) {
  // value is a naive ISO string from /api/meta (last successful scrape). Format
  // it for humans; fall back to "Live deals" if absent/unparseable.
  let label = "Live deals";
  let dateTime: string | undefined;
  if (value) {
    const d = new Date(value.includes("T") ? value : value.replace(" ", "T"));
    if (!Number.isNaN(d.getTime())) {
      dateTime = value;
      label = `Updated ${new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(d)}`;
    }
  }
  return (
    <span
      role="status"
      aria-label={`Deals ${value ? "last updated" : "are live"}`}
      className="hidden items-center gap-1.5 rounded-full border border-border bg-card/70 px-3 py-1.5 text-xs font-medium text-muted-foreground lg:inline-flex"
    >
      <span className="relative flex size-2" aria-hidden="true">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500/60 motion-reduce:hidden" />
        <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
      </span>
      {dateTime ? <time dateTime={dateTime}>{label}</time> : label}
    </span>
  );
}

function LoadingPanel() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-card/40 py-24 text-muted-foreground">
      <Loader2 className="size-7 animate-spin text-primary motion-reduce:animate-none" />
      <p className="text-sm font-medium">Finding free stuff near you…</p>
    </div>
  );
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 rounded-2xl border border-destructive/30 bg-destructive/5 py-24 text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
        <TriangleAlert className="size-7" />
      </div>
      <div>
        <p className="font-heading text-lg font-semibold text-foreground">Couldn&apos;t load deals</p>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">{message}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <RefreshCw className="size-4" />
        Try again
      </button>
    </div>
  );
}
