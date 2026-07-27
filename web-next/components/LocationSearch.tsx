"use client";

import * as React from "react";
import {
  Button,
  IconButton,
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core";
import {
  LocateFixed,
  MapPin,
  Search,
  X,
} from "lucide-react";

import {
  NEIGHBORHOODS_BY_MARKET,
  type SearchOrigin,
} from "@/lib/location";
import {
  isInMarketArea,
  MARKETS,
  type Market,
} from "@/lib/markets";

interface LocationSearchProps {
  market: Market;
  origin: SearchOrigin | null;
  onMarketChange: (market: Market) => void;
  onOriginChange: (origin: SearchOrigin | null) => void;
}

export function LocationSearch({
  market,
  origin,
  onMarketChange,
  onOriginChange,
}: LocationSearchProps) {
  const marketConfig = MARKETS[market];
  const listId = React.useId();
  const requestRef = React.useRef<AbortController | null>(null);
  const [query, setQuery] = React.useState("");
  const [pending, setPending] = React.useState<"search" | "geolocation" | null>(
    null,
  );
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(
    () => () => {
      requestRef.current?.abort();
    },
    [],
  );

  const search = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = query.trim();
    if (!value) return;

    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setPending("search");
    setError(null);
    try {
      const params = new URLSearchParams({ q: value, market });
      const response = await fetch(`/api/geocode?${params}`, {
        signal: controller.signal,
      });
      const payload = (await response.json()) as SearchOrigin & { error?: string };
      if (!response.ok) throw new Error(payload.error || "Location not found.");
      onOriginChange(payload);
      setQuery("");
    } catch (caught) {
      if (controller.signal.aborted) return;
      setError(
        caught instanceof Error ? caught.message : "Location search failed.",
      );
    } finally {
      if (!controller.signal.aborted) setPending(null);
    }
  };

  const locate = () => {
    if (!navigator.geolocation) {
      setError("Location access is not supported by this browser.");
      return;
    }
    setPending("geolocation");
    setError(null);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        // Gate device coords by the same market bounds the address path enforces;
        // an out-of-area origin would center the map on an empty region with no pins.
        if (!isInMarketArea(coords.latitude, coords.longitude, market)) {
          setError(
            `You appear to be outside the ${marketConfig.label} area. Search a neighborhood or address instead.`,
          );
          setPending(null);
          return;
        }
        onOriginChange({
          lat: coords.latitude,
          lng: coords.longitude,
          label: "Your location",
          source: "geolocation",
        });
        setPending(null);
      },
      () => {
        setError("Location access was unavailable. Search an address instead.");
        setPending(null);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 300_000 },
    );
  };

  const changeMarket = (next: string) => {
    requestRef.current?.abort();
    setQuery("");
    setPending(null);
    setError(null);
    onMarketChange(next as Market);
  };

  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <SegmentedControl
          value={market}
          onChange={changeMarket}
          label="Choose a city"
          size="sm"
        >
          <SegmentedControlItem value="seattle" label="Seattle" />
          <SegmentedControlItem value="atlanta" label="Atlanta" />
        </SegmentedControl>
        <form
          onSubmit={search}
          role="search"
          className="flex min-w-[min(100%,18rem)] flex-1 items-center rounded-lg border border-border bg-card shadow-sm focus-within:border-primary/60 focus-within:ring-2 focus-within:ring-ring/20"
        >
          <Search
            className="ml-3 size-4 shrink-0 text-muted-foreground"
            aria-hidden
          />
          <label htmlFor="deal-location-search" className="sr-only">
            Search by {marketConfig.label} neighborhood or address
          </label>
          <input
            id="deal-location-search"
            list={listId}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Neighborhood or address"
            autoComplete="street-address"
            className="min-w-0 flex-1 bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground"
          />
          <datalist id={listId}>
            {NEIGHBORHOODS_BY_MARKET[market].map((neighborhood) => (
              <option key={neighborhood.name} value={neighborhood.name} />
            ))}
          </datalist>
          <IconButton
            type="submit"
            label="Search location"
            tooltip="Search location"
            icon={<Search />}
            size="sm"
            variant="ghost"
            isDisabled={!query.trim() || pending !== null}
            isLoading={pending === "search"}
          />
        </form>

        <Button
          label="Near me"
          icon={<LocateFixed />}
          size="sm"
          variant="secondary"
          onClick={locate}
          isDisabled={pending !== null}
          isLoading={pending === "geolocation"}
        />

        {origin && (
          <span className="inline-flex h-10 max-w-full items-center gap-2 rounded-lg border border-primary/25 bg-primary/8 px-3 text-sm font-medium text-foreground">
            <MapPin className="size-4 shrink-0 text-primary" aria-hidden />
            <span className="max-w-56 truncate">{origin.label}</span>
            <IconButton
              label="Clear location"
              tooltip="Clear location"
              icon={<X />}
              size="sm"
              variant="ghost"
              onClick={() => onOriginChange(null)}
            />
          </span>
        )}
      </div>
      <div
        role="status"
        aria-live="polite"
        className="min-h-5 pt-1 text-xs text-destructive"
      >
        {error}
      </div>
    </div>
  );
}
