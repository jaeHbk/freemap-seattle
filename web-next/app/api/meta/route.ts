import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/meta -> current coverage plus latest per-source run telemetry.
export async function GET() {
  const countRows = await query("SELECT source, COUNT(*) AS n FROM deals GROUP BY source");
  const counts = new Map<string, number>();
  for (const r of countRows) counts.set(r.source as string, Number(r.n));

  const runRows = await query(
    "SELECT source, MAX(finished_at) AS last_ok FROM scrape_runs " +
      "WHERE errors IS NULL AND finished_at IS NOT NULL GROUP BY source",
  );
  const lastOk = new Map<string, string | null>();
  for (const r of runRows) lastOk.set(r.source as string, r.last_ok as string | null);

  let latestRows;
  try {
    latestRows = await query(
      "SELECT s.source, s.finished_at, s.deals_found, s.deals_upserted, " +
        "s.map_pins, s.geocode_failures, s.duration_ms, s.errors " +
        "FROM scrape_runs s JOIN (" +
        "SELECT source, MAX(id) AS latest_id FROM scrape_runs GROUP BY source" +
        ") latest ON s.source = latest.source AND s.id = latest.latest_id",
    );
  } catch {
    // Vercel can deploy before the additive telemetry migration reaches Turso.
    latestRows = await query(
      "SELECT s.source, s.finished_at, s.deals_found, s.errors " +
        "FROM scrape_runs s JOIN (" +
        "SELECT source, MAX(id) AS latest_id FROM scrape_runs GROUP BY source" +
        ") latest ON s.source = latest.source AND s.id = latest.latest_id",
    );
  }

  const latestRuns = new Map<string, {
    finished_at: string | null;
    status: "ok" | "error";
    deals_found: number | null;
    deals_upserted: number | null;
    map_pins: number | null;
    geocode_failures: number | null;
    duration_ms: number | null;
  }>();
  for (const row of latestRows) {
    latestRuns.set(row.source as string, {
      finished_at: row.finished_at as string | null,
      status: row.errors == null ? "ok" : "error",
      deals_found: row.deals_found == null ? null : Number(row.deals_found),
      deals_upserted:
        row.deals_upserted == null ? null : Number(row.deals_upserted),
      map_pins: row.map_pins == null ? null : Number(row.map_pins),
      geocode_failures:
        row.geocode_failures == null ? null : Number(row.geocode_failures),
      duration_ms: row.duration_ms == null ? null : Number(row.duration_ms),
    });
  }

  const sources = [
    ...new Set([...counts.keys(), ...lastOk.keys(), ...latestRuns.keys()]),
  ].sort();
  return Response.json({
    sources: sources.map((s) => ({
      source: s,
      deal_count: counts.get(s) ?? 0,
      last_successful_scrape: lastOk.get(s) ?? null,
      latest_run: latestRuns.get(s) ?? null,
    })),
  });
}
