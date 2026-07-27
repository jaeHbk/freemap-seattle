import { query, rowToDeal, type Deal } from "@/lib/db";
import {
  parseIncludeStale,
  selectDeals,
} from "@/lib/api-contract";
import {
  BboxError,
  naiveLocalIso,
  parseBbox,
  type Bbox,
} from "@/lib/transforms";
import { MARKETS, parseMarket } from "@/lib/markets";

// Reads hit a live DB, so never cache.
export const dynamic = "force-dynamic";

// GET /api/deals?market=&type=&category=&placement=&bbox=&include_stale=
// Explicit bbox queries take precedence. Otherwise physical deals are scoped to
// the selected market while online deals remain available in every market.
export async function GET(request: Request) {
  const sp = new URL(request.url).searchParams;
  const market = parseMarket(sp.get("market"));
  const type = sp.get("type");
  const category = sp.get("category");
  const placement = sp.get("placement");
  const includeStale = parseIncludeStale(sp.get("include_stale"));

  let bbox: Bbox | null;
  try {
    bbox = parseBbox(sp.get("bbox"));
  } catch (e) {
    if (e instanceof BboxError) {
      return Response.json({ error: e.message }, { status: 400 });
    }
    throw e;
  }

  // Push coordinate filters into SQL. Bounds are inclusive and NULL coordinates
  // never satisfy a physical-market comparison.
  // ORDER BY first_seen, id matches scrapers/db.py so collapseDedup's first-seen
  // primary is deterministic (SQLite gives no order without an explicit ORDER BY).
  const rows = bbox
    ? await query(
        "SELECT * FROM deals WHERE lat IS NOT NULL AND lng IS NOT NULL " +
          "AND lng >= ? AND lng <= ? AND lat >= ? AND lat <= ? " +
          "ORDER BY first_seen, id",
        [bbox[0], bbox[2], bbox[1], bbox[3]],
      )
    : await query(
        "SELECT * FROM deals WHERE placement = 'online' OR " +
          "(lat IS NOT NULL AND lng IS NOT NULL " +
          "AND lng >= ? AND lng <= ? AND lat >= ? AND lat <= ?) " +
          "ORDER BY first_seen, id",
        [
          MARKETS[market].bounds.minLng,
          MARKETS[market].bounds.maxLng,
          MARKETS[market].bounds.minLat,
          MARKETS[market].bounds.maxLat,
        ],
      );

  // The scraper writes naive-LOCAL timestamps (datetime.now(), no tz). Python
  // compares them against a naive-local now. computeStatus reads naive strings as
  // UTC, so `now` must ALSO be a naive-local string (not a Date, whose getTime()
  // is true UTC epoch) — else the stale/expired boundary skews by the host's UTC
  // offset and deals are wrongly hidden. Build a naive-local ISO string.
  const now = naiveLocalIso();
  return Response.json(
    selectDeals(
      rows.map(rowToDeal) as Deal[],
      { type, category, placement, includeStale },
      now,
    ),
  );
}
