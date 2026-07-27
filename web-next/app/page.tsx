"use client";

import * as React from "react";
import { Drawer } from "@base-ui/react/drawer";
import {
  AppShell,
  Button,
  Heading,
  IconButton,
  NavIcon,
  StatusDot,
  Text,
  TopNav,
  TopNavHeading,
} from "@astryxdesign/core";
import {
  Bell,
  Heart,
  MapPinned,
  SlidersHorizontal,
  X,
  Loader2,
  TriangleAlert,
  RefreshCw,
} from "lucide-react";

import { Filters } from "@/components/Filters";
import {
  DealAlerts,
  type AlertPermission,
} from "@/components/DealAlerts";
import { DealDetails } from "@/components/DealDetails";
import { DealList } from "@/components/DealList";
import { DealMap } from "@/components/DealMap";
import { LocationSearch } from "@/components/LocationSearch";
import { ViewTabs, type ViewValue, TAB_IDS, PANEL_IDS } from "@/components/ViewTabs";
import {
  buildQuery,
  dealsForList,
  dealsForMap,
  EMPTY_FILTERS,
} from "@/components/deals";
import type { Deal, FilterState } from "@/components/deals";
import {
  ALERTS_STORAGE_KEY,
  DEFAULT_ALERT_PREFERENCES,
  FAVORITES_STORAGE_KEY,
  dealPreferenceKey,
  mergeSeenDealKeys,
  parseAlertPreferences,
  parseFavoriteKeys,
  serializeAlertPreferences,
  serializeFavoriteKeys,
  unseenNearbyDeals,
  type AlertPreferences,
} from "@/lib/deal-preferences";
import {
  sortDealsByDistance,
  type SearchOrigin,
} from "@/lib/location";
import {
  parseUrlState,
  serializeUrlState,
  type AppUrlState,
  type MapViewport,
} from "@/lib/url-state";
import { cn } from "@/lib/utils";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready" };

interface MetaSource {
  last_successful_scrape?: string | null;
}

const ALERT_CHECK_INTERVAL_MS = 15 * 60 * 1000;

async function fetchUnfilteredDeals(): Promise<Deal[]> {
  const response = await fetch("/api/deals");
  if (!response.ok) throw new Error(`Server responded ${response.status}`);
  const data: unknown = await response.json();
  return Array.isArray(data) ? (data as Deal[]) : [];
}

export default function Home() {
  const [filters, setFilters] = React.useState<FilterState>(EMPTY_FILTERS);
  const [view, setView] = React.useState<ViewValue>("map");
  const [deals, setDeals] = React.useState<Deal[]>([]);
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });
  const [freshness, setFreshness] = React.useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [reloadKey, setReloadKey] = React.useState(0);
  const [origin, setOrigin] = React.useState<SearchOrigin | null>(null);
  const [selectedDealId, setSelectedDealId] = React.useState<string | null>(
    null,
  );
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const [mapViewport, setMapViewport] = React.useState<MapViewport | null>(
    null,
  );
  const [urlReady, setUrlReady] = React.useState(false);
  const [fetchedDeal, setFetchedDeal] = React.useState<Deal | null>(null);
  const [favoriteDealKeys, setFavoriteDealKeys] = React.useState<Set<string>>(
    new Set(),
  );
  const [favoritesOnly, setFavoritesOnly] = React.useState(false);
  const [preferencesReady, setPreferencesReady] = React.useState(false);
  const [alertsOpen, setAlertsOpen] = React.useState(false);
  const [alertPreferences, setAlertPreferences] =
    React.useState<AlertPreferences>({
      ...DEFAULT_ALERT_PREFERENCES,
      seenDealKeys: [],
    });
  const [alertPermission, setAlertPermission] =
    React.useState<AlertPermission>("default");
  const [alertPending, setAlertPending] = React.useState(false);
  const [alertError, setAlertError] = React.useState<string | null>(null);
  const automaticAlertCheckStarted = React.useRef(false);

  const applyUrlState = React.useCallback((next: AppUrlState) => {
    setView(next.view);
    setFilters(next.filters);
    setOrigin(next.origin);
    setSelectedDealId(next.selectedDealId);
    setDetailsOpen(next.detailsOpen);
    setMapViewport(next.mapViewport);
  }, []);

  // Read the URL after hydration so server and client render the same initial
  // shell. popstate restores links navigated with browser back/forward.
  React.useEffect(() => {
    const restore = () => {
      applyUrlState(parseUrlState(new URLSearchParams(window.location.search)));
      setUrlReady(true);
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [applyUrlState]);

  React.useEffect(() => {
    if (!urlReady) return;
    const params = serializeUrlState(
      {
        view,
        filters,
        origin,
        selectedDealId,
        detailsOpen,
        mapViewport,
      },
      new URLSearchParams(window.location.search),
    );
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (nextUrl !== currentUrl) {
      window.history.replaceState(window.history.state, "", nextUrl);
    }
  }, [
    detailsOpen,
    filters,
    mapViewport,
    origin,
    selectedDealId,
    urlReady,
    view,
  ]);

  // Fetch deals whenever a SERVER-side filter changes. include_stale is the
  // server's source of truth (the old app's bug was refiltering only in memory);
  // type/category/placement are sent too so the payload stays small.
  React.useEffect(() => {
    if (!urlReady) return;
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
  }, [filters, reloadKey, urlReady]);

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

  React.useEffect(() => {
    const permission: AlertPermission =
      "Notification" in window
        ? Notification.permission
        : "unsupported";
    let storedFavorites: string | null = null;
    let storedAlerts: string | null = null;
    try {
      storedFavorites = window.localStorage.getItem(FAVORITES_STORAGE_KEY);
      storedAlerts = window.localStorage.getItem(ALERTS_STORAGE_KEY);
    } catch {
      // Use defaults when browser storage is unavailable.
    }
    /* eslint-disable react-hooks/set-state-in-effect */
    setFavoriteDealKeys(parseFavoriteKeys(storedFavorites));
    setAlertPreferences(parseAlertPreferences(storedAlerts));
    setAlertPermission(permission);
    setPreferencesReady(true);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  React.useEffect(() => {
    if (!preferencesReady) return;
    try {
      window.localStorage.setItem(
        FAVORITES_STORAGE_KEY,
        serializeFavoriteKeys(favoriteDealKeys),
      );
    } catch {
      // Storage can be unavailable in private browsing; favorites still work
      // for the current page session.
    }
  }, [favoriteDealKeys, preferencesReady]);

  React.useEffect(() => {
    if (!preferencesReady) return;
    try {
      window.localStorage.setItem(
        ALERTS_STORAGE_KEY,
        serializeAlertPreferences(alertPreferences),
      );
    } catch {
      // Keep in-memory alert settings when browser storage is unavailable.
    }
  }, [alertPreferences, preferencesReady]);

  const inMemoryDeal =
    deals.find((deal) => String(deal.id) === selectedDealId) ?? null;

  // Hydrate the details drawer from the single-deal route when the open deal is
  // absent from the loaded payload — a filter change dropped it, or a shared/deep
  // link points at a deal outside the recipient's default set. Waits for the
  // payload (a still-arriving deal is not "missing"); a definitive failure closes
  // the drawer so the URL and UI stop advertising an open detail that never renders.
  React.useEffect(() => {
    if (
      !detailsOpen ||
      !selectedDealId ||
      state.kind !== "ready" ||
      inMemoryDeal
    ) {
      return;
    }
    const ctrl = new AbortController();
    fetch(`/api/deals/${encodeURIComponent(selectedDealId)}`, {
      signal: ctrl.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((deal: Deal) => setFetchedDeal(deal))
      .catch(() => {
        if (ctrl.signal.aborted) return;
        setDetailsOpen(false);
      });
    return () => ctrl.abort();
  }, [detailsOpen, selectedDealId, state.kind, inMemoryDeal]);

  const preferenceFilteredDeals = React.useMemo(
    () =>
      favoritesOnly
        ? deals.filter((deal) =>
            favoriteDealKeys.has(dealPreferenceKey(deal)),
          )
        : deals,
    [deals, favoriteDealKeys, favoritesOnly],
  );
  const mapDeals = React.useMemo(
    () => dealsForMap(preferenceFilteredDeals, filters),
    [preferenceFilteredDeals, filters],
  );
  const listDeals = React.useMemo(
    () =>
      sortDealsByDistance(
        dealsForList(preferenceFilteredDeals, filters),
        origin,
      ),
    [preferenceFilteredDeals, filters, origin],
  );
  const visibleCount = view === "map" ? mapDeals.length : listDeals.length;
  const hasActiveFilters = Boolean(
    filters.type ||
      filters.category ||
      filters.placement ||
      filters.includeStale ||
      favoritesOnly,
  );
  const selectedDeal =
    inMemoryDeal ??
    (fetchedDeal && String(fetchedDeal.id) === selectedDealId
      ? fetchedDeal
      : null);

  const clearFilters = React.useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setFavoritesOnly(false);
  }, []);
  const toggleFavorite = React.useCallback((deal: Deal) => {
    const key = dealPreferenceKey(deal);
    setFavoriteDealKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);
  const selectDeal = React.useCallback(
    (dealId: string) => setSelectedDealId(dealId),
    [],
  );
  const showDealOnMap = React.useCallback(
    (dealId: string) => {
      const deal =
        deals.find((candidate) => String(candidate.id) === dealId) ??
        (fetchedDeal && String(fetchedDeal.id) === dealId ? fetchedDeal : null);
      if (deal?.lat != null && deal.lng != null) {
        const lat = deal.lat;
        const lng = deal.lng;
        setMapViewport((current) => ({
          lat,
          lng,
          zoom: Math.max(current?.zoom ?? 15, 15),
        }));
      }
      setSelectedDealId(dealId);
      setView("map");
    },
    [deals, fetchedDeal],
  );
  const viewDealDetails = React.useCallback((dealId: string) => {
    setSelectedDealId(dealId);
    setDetailsOpen(true);
  }, []);
  const changeOrigin = React.useCallback((next: SearchOrigin | null) => {
    setOrigin(next);
    if (next) {
      setMapViewport((current) => ({
        lat: next.lat,
        lng: next.lng,
        zoom: Math.max(current?.zoom ?? 13, 13),
      }));
    }
  }, []);
  const changeMapViewport = React.useCallback((next: MapViewport) => {
    setMapViewport((current) => {
      if (
        current &&
        Math.abs(current.lat - next.lat) < 0.00001 &&
        Math.abs(current.lng - next.lng) < 0.00001 &&
        Math.abs(current.zoom - next.zoom) < 0.01
      ) {
        return current;
      }
      return next;
    });
  }, []);

  const checkForNewDeals = React.useCallback(async () => {
    if (!origin) {
      setAlertError("Choose a Seattle location before checking for deals.");
      return;
    }
    if (
      alertPermission !== "granted" ||
      !("Notification" in window)
    ) {
      setAlertError("Browser notification permission is required.");
      return;
    }

    setAlertPending(true);
    setAlertError(null);
    try {
      const currentDeals = await fetchUnfilteredDeals();
      const unseen = unseenNearbyDeals(
        currentDeals,
        alertPreferences.seenDealKeys,
        origin,
        alertPreferences.radiusMiles,
      );
      if (unseen.length > 0) {
        const body =
          unseen.length === 1
            ? unseen[0].title
            : `${unseen[0].title} and ${unseen.length - 1} more`;
        try {
          new Notification(
            `${unseen.length} new nearby ${
              unseen.length === 1 ? "deal" : "deals"
            }`,
            { body },
          );
        } catch {
          setAlertError("The browser could not display the notification.");
        }
      }
      setAlertPreferences((current) => ({
        ...current,
        seenDealKeys: mergeSeenDealKeys(
          current.seenDealKeys,
          currentDeals,
        ),
      }));
    } catch (error) {
      setAlertError(
        error instanceof Error ? error.message : "Could not check for deals.",
      );
    } finally {
      setAlertPending(false);
    }
  }, [
    alertPermission,
    alertPreferences.radiusMiles,
    alertPreferences.seenDealKeys,
    origin,
  ]);

  const changeAlertsEnabled = React.useCallback(
    async (enabled: boolean) => {
      if (!enabled) {
        setAlertPreferences((current) => ({ ...current, enabled: false }));
        setAlertError(null);
        return;
      }
      if (!origin) {
        setAlertError("Choose a Seattle location before enabling alerts.");
        return;
      }
      if (!("Notification" in window)) {
        setAlertPermission("unsupported");
        setAlertError("Browser notifications are unavailable.");
        return;
      }

      setAlertPending(true);
      setAlertError(null);
      try {
        const permission =
          Notification.permission === "default"
            ? await Notification.requestPermission()
            : Notification.permission;
        setAlertPermission(permission);
        if (permission !== "granted") {
          setAlertError("Browser notification permission was not granted.");
          return;
        }

        const baselineDeals = await fetchUnfilteredDeals();
        automaticAlertCheckStarted.current = true;
        setAlertPreferences((current) => ({
          ...current,
          enabled: true,
          seenDealKeys: mergeSeenDealKeys(
            current.seenDealKeys,
            baselineDeals,
          ),
        }));
      } catch (error) {
        setAlertError(
          error instanceof Error ? error.message : "Could not enable alerts.",
        );
      } finally {
        setAlertPending(false);
      }
    },
    [origin],
  );

  React.useEffect(() => {
    if (
      !preferencesReady ||
      !alertPreferences.enabled ||
      !origin ||
      alertPermission !== "granted"
    ) {
      return;
    }
    if (!automaticAlertCheckStarted.current) {
      automaticAlertCheckStarted.current = true;
      void checkForNewDeals();
    }
    const interval = window.setInterval(
      () => void checkForNewDeals(),
      ALERT_CHECK_INTERVAL_MS,
    );
    return () => window.clearInterval(interval);
  }, [
    alertPermission,
    alertPreferences.enabled,
    checkForNewDeals,
    origin,
    preferencesReady,
  ]);

  return (
    <AppShell
      height="fill"
      variant="section"
      contentPadding={0}
      mobileNav={false}
      topNav={
        <TopNav
          label="FreeMap navigation"
          heading={
            <TopNavHeading
              logo={<NavIcon icon={<MapPinned />} />}
              heading="FreeMap"
              subheading="Seattle"
              headingHref="/"
            />
          }
          startContent={
            <ViewTabs
              value={view}
              onValueChange={setView}
              mapCount={mapDeals.length}
              listCount={listDeals.length}
            />
          }
          endContent={
            <div className="flex items-center gap-1">
              <FreshnessBadge value={freshness} />
              <span className="relative inline-flex">
                <IconButton
                  label={
                    favoritesOnly ? "Show all deals" : "Show favorites only"
                  }
                  tooltip={
                    favoritesOnly ? "Show all deals" : "Show favorites only"
                  }
                  icon={
                    <Heart
                      fill={favoritesOnly ? "currentColor" : "none"}
                    />
                  }
                  variant={favoritesOnly ? "primary" : "ghost"}
                  size="sm"
                  aria-pressed={favoritesOnly}
                  onClick={() => setFavoritesOnly((current) => !current)}
                />
                {favoriteDealKeys.size > 0 && (
                  <span className="absolute -right-1 -top-1 flex min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[0.625rem] font-semibold leading-4 text-primary-foreground">
                    {favoriteDealKeys.size}
                  </span>
                )}
              </span>
              <span className="relative inline-flex">
                <IconButton
                  label="Open deal alerts"
                  tooltip="Deal alerts"
                  icon={<Bell />}
                  variant="ghost"
                  size="sm"
                  onClick={() => setAlertsOpen(true)}
                />
                {alertPreferences.enabled && (
                  <span
                    className="absolute right-1 top-1 size-2 rounded-full border-2 border-background bg-emerald-500"
                    aria-hidden="true"
                  />
                )}
              </span>
              <span className="md:hidden">
                <IconButton
                  label="Open filters"
                  tooltip="Filters"
                  icon={<SlidersHorizontal />}
                  variant="secondary"
                  size="sm"
                  onClick={() => setDrawerOpen(true)}
                />
              </span>
            </div>
          }
        />
      }
    >
      <Heading level={1} className="sr-only">
        FreeMap Seattle, free and BOGO deals
      </Heading>

      <div className="mx-auto flex h-full w-full max-w-[1440px] gap-5 px-4 py-4 sm:px-5">
        <aside
          className="hidden w-60 shrink-0 border-r border-border pr-5 md:block"
          aria-label="Filters"
        >
          <div className="sticky top-0">
            <div className="mb-5 flex items-center gap-2">
              <SlidersHorizontal className="size-4 text-primary" aria-hidden />
              <Text type="label" weight="semibold">
                Filter deals
              </Text>
            </div>
            <Filters
              state={filters}
              onChange={setFilters}
              idPrefix="desktop"
              count={visibleCount}
            />
          </div>
        </aside>

        <div id="main" className="flex min-w-0 flex-1 flex-col">
          <LocationSearch origin={origin} onOriginChange={changeOrigin} />
          {state.kind === "error" ? (
            <ErrorPanel message={state.message} onRetry={() => setReloadKey((k) => k + 1)} />
          ) : state.kind === "loading" ? (
            <LoadingPanel />
          ) : view === "map" ? (
            <section
              id={PANEL_IDS.map}
              role="region"
              aria-labelledby={TAB_IDS.map}
              tabIndex={0}
              className="h-[calc(100dvh-8.5rem)] min-h-[420px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <DealMap
                deals={mapDeals}
                origin={origin}
                selectedDealId={selectedDealId}
                viewport={mapViewport}
                onSelectDeal={selectDeal}
                onViewDetails={viewDealDetails}
                onViewportChange={changeMapViewport}
                onClearFilters={hasActiveFilters ? clearFilters : undefined}
              />
            </section>
          ) : (
            <section
              id={PANEL_IDS.list}
              role="region"
              aria-labelledby={TAB_IDS.list}
              tabIndex={0}
              className="min-h-0 focus-visible:outline-none"
            >
              <DealList
                deals={listDeals}
                origin={origin}
                selectedDealId={selectedDealId}
                favoriteDealKeys={favoriteDealKeys}
                onSelectDeal={selectDeal}
                onToggleFavorite={toggleFavorite}
                onShowOnMap={showDealOnMap}
                onViewDetails={viewDealDetails}
                onClearFilters={clearFilters}
              />
            </section>
          )}
        </div>
      </div>

      <Drawer.Root
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        swipeDirection="right"
      >
        <Drawer.Portal>
          <Drawer.Backdrop className="fixed inset-0 z-[900] bg-black/40 backdrop-blur-sm transition-opacity data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 motion-reduce:transition-none" />
          <Drawer.Viewport className="pointer-events-none fixed inset-0 z-[1000]">
            <Drawer.Popup
              className={cn(
                "pointer-events-auto fixed inset-y-0 right-0 flex w-[min(20rem,90vw)] flex-col border-l border-border bg-background p-6 shadow-2xl",
                "transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] data-[ending-style]:translate-x-full data-[starting-style]:translate-x-full motion-reduce:transition-none"
              )}
            >
              <div className="mb-5 flex items-center justify-between">
                <Drawer.Title className="text-lg font-semibold text-foreground">
                  Filters
                </Drawer.Title>
                <Drawer.Close
                  className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Close filters"
                >
                  <X className="size-4" />
                </Drawer.Close>
              </div>
              <Filters
                state={filters}
                onChange={setFilters}
                idPrefix="mobile"
                count={visibleCount}
              />
            </Drawer.Popup>
          </Drawer.Viewport>
        </Drawer.Portal>
      </Drawer.Root>

      <DealDetails
        deal={selectedDeal}
        open={detailsOpen}
        favorite={
          selectedDeal
            ? favoriteDealKeys.has(dealPreferenceKey(selectedDeal))
            : false
        }
        onOpenChange={setDetailsOpen}
        onToggleFavorite={toggleFavorite}
        onShowOnMap={showDealOnMap}
      />
      <DealAlerts
        open={alertsOpen}
        onOpenChange={setAlertsOpen}
        enabled={alertPreferences.enabled}
        radiusMiles={alertPreferences.radiusMiles}
        origin={origin}
        permission={alertPermission}
        pending={alertPending}
        error={alertError}
        onEnabledChange={changeAlertsEnabled}
        onRadiusChange={(radiusMiles) =>
          setAlertPreferences((current) => ({
            ...current,
            radiusMiles,
          }))
        }
        onCheckNow={checkForNewDeals}
      />
    </AppShell>
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
      className="hidden items-center gap-2 px-2 lg:inline-flex"
    >
      <StatusDot variant="success" label="Deal data is live" isPulsing />
      <Text type="supporting">
        {dateTime ? <time dateTime={dateTime}>{label}</time> : label}
      </Text>
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
      <Button
        label="Try again"
        variant="primary"
        icon={<RefreshCw />}
        onClick={onRetry}
      />
    </div>
  );
}
