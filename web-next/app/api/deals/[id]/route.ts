import { query, rowToDeal } from "@/lib/db";

export const dynamic = "force-dynamic";

// GET /api/deals/{id} -> single row or 404. 1:1 with api/main.py deal_detail.
export async function GET(_request: Request, ctx: RouteContext<"/api/deals/[id]">) {
  const { id } = await ctx.params;
  const rows = await query("SELECT * FROM deals WHERE id = ?", [id]);
  if (rows.length === 0) {
    return Response.json({ error: "deal not found" }, { status: 404 });
  }
  return Response.json(rowToDeal(rows[0]));
}
