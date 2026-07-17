import { expect, test, type Page } from "@playwright/test";

import type { Deal } from "../components/deals";

const ACTIVE_DEALS: Deal[] = [
  {
    id: 101,
    source: "places_brand",
    source_id: "coffee-101",
    dedup_key: "coffee",
    title: "Free birthday coffee",
    url: "https://example.com/coffee",
    description: "A free handcrafted birthday drink.",
    eligibility: "Rewards members with one prior purchase.",
    redemption: "Scan the member barcode at checkout.",
    verified_at: "2026-07-16T00:00:00",
    deal_type: "free",
    category: "food",
    placement: "physical",
    lat: 47.6231,
    lng: -122.3165,
    raw_location: "Capitol Hill, Seattle",
    geocode_status: "ok",
    posted_at: null,
    expires_at: "2027-07-16T00:00:00",
    first_seen: "2026-07-16T00:00:00",
    last_seen: "2026-07-16T00:00:00",
    status: "active",
    alt_urls: ["https://example.com/coffee-terms"],
  },
  {
    id: 102,
    source: "places_brand",
    source_id: "retail-102",
    dedup_key: "retail",
    title: "Buy one shirt, get one free",
    url: "https://example.com/retail",
    description: "A verified in-store BOGO offer.",
    eligibility: "All visitors.",
    redemption: "Present the offer before payment.",
    verified_at: "2026-07-16T00:00:00",
    deal_type: "bogo",
    category: "retail",
    placement: "physical",
    lat: 47.6687,
    lng: -122.386,
    raw_location: "Ballard, Seattle",
    geocode_status: "ok",
    posted_at: null,
    expires_at: null,
    first_seen: "2026-07-16T00:00:00",
    last_seen: "2026-07-16T00:00:00",
    status: "active",
    alt_urls: [],
  },
  {
    id: 103,
    source: "reddit",
    source_id: "event-103",
    dedup_key: "event",
    title: "Free online community workshop",
    url: "https://example.com/workshop",
    description: "A no-cost online event.",
    eligibility: null,
    redemption: null,
    verified_at: null,
    deal_type: "free",
    category: "event",
    placement: "online",
    lat: null,
    lng: null,
    raw_location: null,
    geocode_status: "n/a",
    posted_at: null,
    expires_at: null,
    first_seen: "2026-07-16T00:00:00",
    last_seen: "2026-07-16T00:00:00",
    status: "active",
    alt_urls: [],
  },
];

const STALE_DEAL: Deal = {
  ...ACTIVE_DEALS[0],
  id: 104,
  source_id: "stale-104",
  dedup_key: "stale",
  title: "Free stale sample",
  lat: 47.651,
  lng: -122.3504,
  raw_location: "Fremont, Seattle",
  status: "stale",
};

const TEST_STYLE = {
  version: 8 as const,
  name: "FreeMap test style",
  glyphs: "https://tiles.test/fonts/{fontstack}/{range}.pbf",
  sources: {},
  layers: [
    {
      id: "background",
      type: "background" as const,
      paint: { "background-color": "#e5e7eb" },
    },
  ],
};

const browserErrors = new WeakMap<Page, string[]>();

async function mockBoundaries(page: Page) {
  await page.route("https://tiles.openfreemap.org/styles/liberty", (route) =>
    route.fulfill({ json: TEST_STYLE }),
  );
  await page.route("https://tiles.test/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body: Buffer.alloc(0),
    }),
  );
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/deals") {
      const includeStale = url.searchParams.get("include_stale") === "true";
      const deals = [...ACTIVE_DEALS, STALE_DEAL].filter((deal) => {
        if (deal.status === "stale" && !includeStale) return false;
        const type = url.searchParams.get("type");
        const category = url.searchParams.get("category");
        const placement = url.searchParams.get("placement");
        return (
          (!type || deal.deal_type === type) &&
          (!category || deal.category === category) &&
          (!placement || deal.placement === placement)
        );
      });
      await route.fulfill({ json: deals });
      return;
    }
    if (url.pathname === "/api/meta") {
      await route.fulfill({
        json: {
          sources: [
            {
              source: "places_brand",
              deal_count: 3,
              last_successful_scrape: "2026-07-16T12:00:00",
              latest_run: {
                status: "ok",
                deals_found: 3,
                deals_upserted: 3,
                map_pins: 2,
                geocode_failures: 0,
                duration_ms: 125,
              },
            },
          ],
        },
      });
      return;
    }
    if (url.pathname === "/api/geocode") {
      await route.fulfill({
        json: {
          lat: 47.6687,
          lng: -122.386,
          label: "Ballard",
          source: "search",
        },
      });
      return;
    }
    await route.fulfill({ status: 404, json: { error: "Not mocked" } });
  });
}

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  browserErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await mockBoundaries(page);
});

test.afterEach(async ({ page }) => {
  expect(browserErrors.get(page) ?? []).toEqual([]);
});

test("list filters and structured deal details survive reload", async ({
  page,
}) => {
  await page.goto("/?view=list&utm_source=e2e");

  await expect(page.locator("[data-deal-id]")).toHaveCount(3);
  await page.getByLabel("Deal type").click();
  await page.getByRole("option", { name: "BOGO" }).click();

  await expect(page.locator("[data-deal-id]")).toHaveCount(1);
  await expect(page.locator('[data-deal-id="102"]')).toContainText(
    "Buy one shirt, get one free",
  );
  await expect.poll(() => new URL(page.url()).searchParams.get("type")).toBe(
    "bogo",
  );

  await page.getByRole("button", { name: "Clear filters" }).click();
  const coffee = page.locator('[data-deal-id="101"]');
  await coffee.getByRole("button", { name: "Details" }).click();

  await expect(page.getByText("Deal details", { exact: true })).toBeVisible();
  await expect(page.getByText("Rewards members with one prior purchase.")).toBeVisible();
  await expect(page.getByText("Scan the member barcode at checkout.")).toBeVisible();
  await expect.poll(() => new URL(page.url()).searchParams.get("deal")).toBe(
    "101",
  );
  await expect.poll(() => new URL(page.url()).searchParams.get("details")).toBe(
    "1",
  );
  expect(new URL(page.url()).searchParams.get("utm_source")).toBe("e2e");

  await page.reload();
  await expect(page.getByText("Deal details", { exact: true })).toBeVisible();
  await expect(page.locator("#tab-list")).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.getByRole("button", { name: "Close deal details" }).click();
  await page
    .locator('[data-deal-id="103"]')
    .getByRole("button", { name: "Details" })
    .click();
  const verifiedValue = page
    .getByText("Verified", { exact: true })
    .locator("xpath=following-sibling::dd[1]");
  await expect(verifiedValue).toHaveText("Not supplied");
  const checkedValue = page
    .getByText("Last checked", { exact: true })
    .locator("xpath=following-sibling::dd[1]");
  await expect(checkedValue).toHaveText("Jul 16, 2026");
});

test("map, selected deal, location, distance order, and camera stay synchronized", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator('[data-map-deal-target="101"]')).toBeVisible();

  await page.locator('[data-map-deal-target="101"]').focus();
  await page.locator('[data-map-deal-target="101"]').press("Enter");
  await expect(page.locator(".fm-popup-title")).toHaveText(
    "Free birthday coffee",
  );
  await page.locator(".fm-popup-detail").click();
  await expect(page.getByText("Deal details", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close deal details" }).click();

  const beforeZoom = new URL(page.url()).searchParams.get("map");
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect
    .poll(() => new URL(page.url()).searchParams.get("map"))
    .not.toBe(beforeZoom);

  await page
    .getByLabel("Search by Seattle neighborhood or address")
    .fill("Ballard");
  await page.getByRole("button", { name: "Search location" }).click();
  await expect(page.getByText("Ballard", { exact: true })).toBeVisible();
  await expect
    .poll(() => new URL(page.url()).searchParams.get("origin_label"))
    .toBe("Ballard");

  await page.getByRole("tab", { name: /List/ }).click();
  const dealIds = await page
    .locator("[data-deal-id]")
    .evaluateAll((elements) =>
      elements.map((element) => (element as HTMLElement).dataset.dealId),
    );
  expect(dealIds).toEqual(["102", "101", "103"]);
  await expect(page.locator('[data-deal-id="102"]')).toContainText("<0.1 mi");
});

test.describe("mobile", () => {
  test.use({
    viewport: { width: 390, height: 844 },
    permissions: ["geolocation"],
    geolocation: { latitude: 47.61, longitude: -122.33 },
  });

  test("filter drawer and near-me state remain usable without overflow", async ({
    page,
  }) => {
    await page.goto("/?view=list");
    await page.getByRole("button", { name: "Open filters" }).click();
    const filterDialog = page.getByRole("dialog", { name: "Filters" });
    await expect(filterDialog).toBeVisible();
    const duplicateIds = await page.locator("[id]").evaluateAll((elements) => {
      const ids = elements.map((element) => element.id);
      return ids.filter((id, index) => ids.indexOf(id) !== index);
    });
    expect(duplicateIds).toEqual([]);

    await filterDialog.getByLabel("Category").click();
    await page.getByRole("option", { name: "Retail" }).click();
    await expect(
      filterDialog.getByText("1 deal match", { exact: true }),
    ).toBeVisible();
    await filterDialog.getByRole("button", { name: "Close filters" }).click();

    await page.getByRole("button", { name: "Near me" }).click();
    await expect(page.getByText("Your location", { exact: true })).toBeVisible();
    await expect
      .poll(() => new URL(page.url()).searchParams.get("origin_source"))
      .toBe("geolocation");
    expect(new URL(page.url()).searchParams.get("category")).toBe("retail");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
