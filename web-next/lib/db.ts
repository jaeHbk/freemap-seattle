import "server-only";

import { createClient, type Client, type Row } from "@libsql/client";

// Live path: Turso via env. Local dev: the repo's sqlite file. NEVER hardcode a
// token — authToken comes from env only.
// ponytail: one shared client; route handlers are short-lived, libSQL pools internally.
let _client: Client | null = null;

// Local-dev fallback DB, relative to web-next/ (../db/deals.db at repo root). NOT
// an absolute home-dir path — that leaks into the deployed artifact and is wrong
// on Vercel's Linux runtime anyway.
const LOCAL_DB_URL = "file:../db/deals.db";

export function getClient(): Client {
  if (_client) return _client;
  const url = process.env.TURSO_DATABASE_URL;
  const authToken = process.env.TURSO_AUTH_TOKEN;
  if ((url && !authToken) || (!url && authToken)) {
    throw new Error(
      "TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must be set together.",
    );
  }
  // In production (Vercel) the Turso URL is REQUIRED. Without this guard a missing
  // or typo'd env var silently falls back to a nonexistent local file and surfaces
  // as an opaque request-time 500; fail fast with a clear message instead.
  if (
    (!url || !authToken) &&
    (process.env.VERCEL || process.env.NODE_ENV === "production")
  ) {
    throw new Error(
      "Turso credentials are not set. Configure TURSO_DATABASE_URL and " +
        "TURSO_AUTH_TOKEN in Vercel; see docs/DEPLOY.md.",
    );
  }
  _client = createClient({
    url: url ?? LOCAL_DB_URL,
    authToken,
  });
  return _client;
}

// The deals-table row as the read API serves it. `status` is computed at read
// time (compute_status); `alt_urls` is a runtime array (dedup-collapse).
export type Deal = {
  id: number;
  source: string;
  source_id: string;
  dedup_key: string | null;
  title: string;
  url: string;
  description: string | null;
  eligibility: string | null;
  redemption: string | null;
  verified_at: string | null;
  deal_type: "free" | "bogo" | "other";
  category: "food" | "retail" | "event" | "other";
  placement: "physical" | "online";
  lat: number | null;
  lng: number | null;
  raw_location: string | null;
  geocode_status: "ok" | "failed" | "n/a" | "pending";
  posted_at: string | null;
  expires_at: string | null;
  first_seen: string | null;
  last_seen: string | null;
  status?: "active" | "stale" | "expired";
  alt_urls: string[];
};

// rowToDeal: mirror Python _row_to_deal — explicit columns, alt_urls seeded empty.
export function rowToDeal(row: Row): Deal {
  return {
    id: row.id as number,
    source: row.source as string,
    source_id: row.source_id as string,
    dedup_key: row.dedup_key as string | null,
    title: row.title as string,
    url: row.url as string,
    description: row.description as string | null,
    eligibility: row.eligibility as string | null,
    redemption: row.redemption as string | null,
    verified_at: row.verified_at as string | null,
    deal_type: row.deal_type as Deal["deal_type"],
    category: row.category as Deal["category"],
    placement: row.placement as Deal["placement"],
    lat: row.lat as number | null,
    lng: row.lng as number | null,
    raw_location: row.raw_location as string | null,
    geocode_status: row.geocode_status as Deal["geocode_status"],
    posted_at: row.posted_at as string | null,
    expires_at: row.expires_at as string | null,
    first_seen: row.first_seen as string | null,
    last_seen: row.last_seen as string | null,
    alt_urls: [],
  };
}

// query: thin helper so route handlers don't repeat getClient().execute(...).
export async function query(sql: string, args: unknown[] = []): Promise<Row[]> {
  const rs = await getClient().execute({ sql, args: args as never });
  return rs.rows;
}
