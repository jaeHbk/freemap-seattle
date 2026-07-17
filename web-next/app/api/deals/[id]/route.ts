import { query, rowToDeal } from "@/lib/db";
import { parseDealId } from "@/lib/api-contract";
import { computeStatus, naiveLocalIso } from "@/lib/transforms";

export const dynamic = "force-dynamic";

// GET /api/deals/{id} -> single row (with read-time status) or 404. status is
// computed here exactly as the list route does, so a deal fetched by id is a
// complete Deal (the client renders deal.status and refilters on it).
export async function GET(_request: Request, ctx: RouteContext<"/api/deals/[id]">) {
  const { id } = await ctx.params;
  const dealId = parseDealId(id);
  if (dealId === null) {
    return Response.json(
      { error: "deal id must be an integer" },
      { status: 422 },
    );
  }
  const rows = await query("SELECT * FROM deals WHERE id = ?", [dealId]);
  if (rows.length === 0) {
    return Response.json({ error: "deal not found" }, { status: 404 });
  }
  const deal = rowToDeal(rows[0]);
  const status = computeStatus(deal.expires_at, deal.last_seen, naiveLocalIso());
  return Response.json({ ...deal, status });
}
