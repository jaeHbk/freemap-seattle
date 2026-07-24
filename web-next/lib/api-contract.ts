import type { Deal } from "./db";
import { collapseDedup, computeStatus } from "./transforms.ts";

export interface DealQueryOptions {
  type: string | null;
  category: string | null;
  placement: string | null;
  includeStale: boolean;
}

type SourceRow = {
  source?: unknown;
  [column: string]: unknown;
};

export function parseIncludeStale(value: string | null): boolean {
  return ["true", "1", "yes", "on"].includes((value ?? "").toLowerCase());
}

export function parseDealId(value: string): number | null {
  if (!/^-?\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}

export function selectDeals(
  deals: Deal[],
  options: DealQueryOptions,
  now: string,
): Deal[] {
  const selected: Deal[] = [];
  for (const deal of deals) {
    const status = computeStatus(deal.expires_at, deal.last_seen, now);
    if (status === "expired") continue;
    if (status === "stale" && !options.includeStale) continue;
    if (options.type !== null && deal.deal_type !== options.type) continue;
    if (options.category !== null && deal.category !== options.category) {
      continue;
    }
    if (options.placement !== null && deal.placement !== options.placement) {
      continue;
    }
    selected.push({ ...deal, alt_urls: [...deal.alt_urls], status });
  }
  return collapseDedup(selected);
}

export function buildSourceMetadata(
  countRows: SourceRow[],
  successfulRunRows: SourceRow[],
  latestRunRows: SourceRow[],
) {
  const counts = new Map<string, number>();
  for (const row of countRows) {
    counts.set(String(row.source), Number(row.n));
  }

  const lastSuccessful = new Map<string, string | null>();
  for (const row of successfulRunRows) {
    lastSuccessful.set(
      String(row.source),
      row.last_ok == null ? null : String(row.last_ok),
    );
  }

  const numberOrNull = (value: unknown) =>
    value == null ? null : Number(value);
  const latestRuns = new Map<
    string,
    {
      finished_at: string | null;
      status: "ok" | "error";
      deals_found: number | null;
      deals_upserted: number | null;
      map_pins: number | null;
      geocode_failures: number | null;
      candidates_staged: number | null;
      candidates_pending: number | null;
      candidates_rejected: number | null;
      duration_ms: number | null;
    }
  >();
  for (const row of latestRunRows) {
    latestRuns.set(String(row.source), {
      finished_at:
        row.finished_at == null ? null : String(row.finished_at),
      status: row.errors == null ? "ok" : "error",
      deals_found: numberOrNull(row.deals_found),
      deals_upserted: numberOrNull(row.deals_upserted),
      map_pins: numberOrNull(row.map_pins),
      geocode_failures: numberOrNull(row.geocode_failures),
      candidates_staged: numberOrNull(row.candidates_staged),
      candidates_pending: numberOrNull(row.candidates_pending),
      candidates_rejected: numberOrNull(row.candidates_rejected),
      duration_ms: numberOrNull(row.duration_ms),
    });
  }

  const sources = [
    ...new Set([
      ...counts.keys(),
      ...lastSuccessful.keys(),
      ...latestRuns.keys(),
    ]),
  ].sort();
  return {
    sources: sources.map((source) => ({
      source,
      deal_count: counts.get(source) ?? 0,
      last_successful_scrape: lastSuccessful.get(source) ?? null,
      latest_run: latestRuns.get(source) ?? null,
    })),
  };
}
