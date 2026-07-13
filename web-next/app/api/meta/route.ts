import { query } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/meta -> per-source deal_count + last_successful_scrape. 1:1 with
// api/main.py meta: counts from the serving table; last OK scrape (errors IS
// NULL) per source from scrape_runs; sources = union, sorted.
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

  const sources = [...new Set([...counts.keys(), ...lastOk.keys()])].sort();
  return Response.json({
    sources: sources.map((s) => ({
      source: s,
      deal_count: counts.get(s) ?? 0,
      last_successful_scrape: lastOk.get(s) ?? null,
    })),
  });
}
