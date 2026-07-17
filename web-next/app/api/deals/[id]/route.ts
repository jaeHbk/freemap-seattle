import { query, rowToDeal } from "@/lib/db";
import { parseDealId } from "@/lib/api-contract";

export const dynamic = "force-dynamic";

// GET /api/deals/{id} -> single row or 404.
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
  return Response.json(rowToDeal(rows[0]));
}
