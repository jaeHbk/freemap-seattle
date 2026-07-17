import { expect, test } from "@playwright/test";

test("deal routes preserve filtering, freshness, bbox, and dedup behavior", async ({
  request,
}) => {
  const base = await request.get("/api/deals");
  expect(base.ok()).toBe(true);
  const baseDeals = await base.json();
  expect(baseDeals.map((deal: { id: number }) => deal.id)).toEqual([
    1, 2, 5, 6,
  ]);
  expect(baseDeals[0].alt_urls).toEqual(["https://example.com/r7"]);

  const stale = await request.get("/api/deals?include_stale=true");
  expect((await stale.json()).map((deal: { id: number }) => deal.id)).toEqual([
    3, 1, 2, 5, 6,
  ]);

  const filtered = await request.get(
    "/api/deals?type=bogo&category=retail&placement=physical",
  );
  expect((await filtered.json()).map((deal: { id: number }) => deal.id)).toEqual([
    2,
  ]);

  const bbox = await request.get(
    "/api/deals?bbox=-122.45,47.50,-122.20,47.75",
  );
  expect((await bbox.json()).map((deal: { id: number }) => deal.id)).toEqual([
    1,
  ]);

  for (const value of ["garbage", "1,2,3", "1,2,inf,4"]) {
    const invalid = await request.get(
      `/api/deals?bbox=${encodeURIComponent(value)}`,
    );
    expect(invalid.status()).toBe(400);
  }
});

test("detail and metadata routes preserve their HTTP contracts", async ({
  request,
}) => {
  const detail = await request.get("/api/deals/2");
  expect(detail.ok()).toBe(true);
  await expect(detail.json()).resolves.toMatchObject({
    id: 2,
    eligibility: "All visitors.",
    redemption: "Present the offer before payment.",
    verified_at: "2026-07-16T00:00:00",
  });

  expect((await request.get("/api/deals/9999")).status()).toBe(404);
  expect((await request.get("/api/deals/not-an-int")).status()).toBe(422);

  const metadata = await (await request.get("/api/meta")).json();
  expect(metadata.sources).toEqual([
    {
      source: "places_brand",
      deal_count: 3,
      last_successful_scrape: "2026-07-16T12:00:00",
      latest_run: {
        finished_at: "2026-07-16T12:00:00",
        status: "ok",
        deals_found: 3,
        deals_upserted: 3,
        map_pins: 1,
        geocode_failures: 0,
        duration_ms: 500,
      },
    },
    {
      source: "reddit",
      deal_count: 4,
      last_successful_scrape: "2026-07-16T12:00:00",
      latest_run: {
        finished_at: "2026-07-16T12:00:00",
        status: "ok",
        deals_found: 4,
        deals_upserted: 4,
        map_pins: 3,
        geocode_failures: 1,
        duration_ms: 1000,
      },
    },
  ]);
});
