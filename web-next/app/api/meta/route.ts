import { query } from "@/lib/db";
import { buildSourceMetadata } from "@/lib/api-contract";

export const dynamic = "force-dynamic";

// GET /api/meta -> current coverage plus latest per-source run telemetry.
export async function GET() {
  const countRows = await query("SELECT source, COUNT(*) AS n FROM deals GROUP BY source");

  const runRows = await query(
    "SELECT source, MAX(finished_at) AS last_ok FROM scrape_runs " +
      "WHERE errors IS NULL AND finished_at IS NOT NULL GROUP BY source",
  );
  let latestRows;
  try {
    latestRows = await query(
      "SELECT s.source, s.finished_at, s.deals_found, s.deals_upserted, " +
        "s.map_pins, s.geocode_failures, s.candidates_staged, " +
        "s.candidates_pending, s.candidates_rejected, s.duration_ms, s.errors " +
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

  return Response.json(
    buildSourceMetadata(countRows, runRows, latestRows),
  );
}
