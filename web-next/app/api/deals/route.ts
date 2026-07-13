import { query, rowToDeal, type Deal } from "@/lib/db";
import {
  BboxError,
  collapseDedup,
  computeStatus,
  naiveLocalIso,
  parseBbox,
  type Bbox,
} from "@/lib/transforms";

// Reads hit a live DB, so never cache.
export const dynamic = "force-dynamic";

// GET /api/deals?type=&category=&placement=&bbox=&include_stale=
// 1:1 port of api/main.py list_deals: load deals (bbox -> SQL coord filter, else
// all), compute status at read time, drop expired, drop stale unless
// include_stale, apply equality filters, collapse dedup groups.
export async function GET(request: Request) {
  const sp = new URL(request.url).searchParams;
  const type = sp.get("type");
  const category = sp.get("category");
  const placement = sp.get("placement");
  // Match FastAPI bool query coercion (true/True/1/yes/on), not just literal "true",
  // so a hand-built or non-app client can't silently get the non-stale set.
  const includeStale = ["true", "1", "yes", "on"].includes(
    (sp.get("include_stale") ?? "").toLowerCase(),
  );

  let bbox: Bbox | null;
  try {
    bbox = parseBbox(sp.get("bbox"));
  } catch (e) {
    if (e instanceof BboxError) {
      return Response.json({ error: e.message }, { status: 400 });
    }
    throw e;
  }

  // With a bbox, push the coord filter into SQL (excludes coordless deals); else
  // serve every deal. inclusive bounds; NULL lat/lng never satisfy a comparison.
  // ORDER BY first_seen, id matches scrapers/db.py so collapseDedup's first-seen
  // primary is deterministic (SQLite gives no order without an explicit ORDER BY).
  const rows = bbox
    ? await query(
        "SELECT * FROM deals WHERE lat IS NOT NULL AND lng IS NOT NULL " +
          "AND lng >= ? AND lng <= ? AND lat >= ? AND lat <= ? " +
          "ORDER BY first_seen, id",
        [bbox[0], bbox[2], bbox[1], bbox[3]],
      )
    : await query("SELECT * FROM deals ORDER BY first_seen, id");

  // The scraper writes naive-LOCAL timestamps (datetime.now(), no tz). Python
  // compares them against a naive-local now. computeStatus reads naive strings as
  // UTC, so `now` must ALSO be a naive-local string (not a Date, whose getTime()
  // is true UTC epoch) — else the stale/expired boundary skews by the host's UTC
  // offset and deals are wrongly hidden. Build a naive-local ISO string.
  const now = naiveLocalIso();
  const out: Deal[] = [];
  for (const row of rows) {
    const status = computeStatus(
      row.expires_at as string | null,
      row.last_seen as string | null,
      now,
    );
    if (status === "expired") continue;
    if (status === "stale" && !includeStale) continue;
    const deal = rowToDeal(row);
    deal.status = status;
    if (type !== null && deal.deal_type !== type) continue;
    if (category !== null && deal.category !== category) continue;
    if (placement !== null && deal.placement !== placement) continue;
    out.push(deal);
  }
  return Response.json(collapseDedup(out));
}
