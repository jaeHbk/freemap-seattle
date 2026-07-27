import { readFile, rm } from "node:fs/promises";
import path from "node:path";
import { createClient } from "@libsql/client";

import {
  E2E_DATABASE_PATH,
  E2E_DATABASE_URL,
} from "./database";

const INSERT_DEAL = `
  INSERT INTO deals (
    id, source, source_id, dedup_key, title, url, description,
    eligibility, redemption, verified_at, deal_type, category, placement,
    lat, lng, raw_location, geocode_status, posted_at, expires_at,
    first_seen, last_seen, status
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`;

export default async function globalSetup() {
  for (const suffix of ["", "-shm", "-wal"]) {
    await rm(`${E2E_DATABASE_PATH}${suffix}`, { force: true });
  }

  const client = createClient({ url: E2E_DATABASE_URL });
  const schema = await readFile(
    path.resolve(process.cwd(), "../db/schema.sql"),
    "utf8",
  );
  await client.executeMultiple(schema);

  const future = "2099-12-31T00:00:00";
  const fresh = "2099-01-01T00:00:00";
  const old = "2000-01-01T00:00:00";
  const rows = [
    [
      1, "reddit", "r1", "coffee", "Free coffee", "https://example.com/r1",
      "Free drip coffee.", null, null, null, "free", "food", "physical",
      47.62, -122.32, "Capitol Hill", "ok", fresh, future, fresh, fresh,
      "active",
    ],
    [
      2, "places_brand", "p2", "shirt", "Buy one shirt, get one free",
      "https://example.com/p2", "A verified BOGO offer.", "All visitors.",
      "Present the offer before payment.", "2026-07-16T00:00:00", "bogo",
      "retail", "physical", 47.6, -121.0, "Bellevue", "ok", fresh, future,
      fresh, fresh, "active",
    ],
    [
      3, "reddit", "r3", "stale", "Stale free pizza",
      "https://example.com/r3", null, null, null, null, "free", "food",
      "physical", 47.61, -122.33, "Ballard", "ok", old, future, old, old,
      "active",
    ],
    [
      4, "places_brand", "p4", "expired", "Expired free event",
      "https://example.com/p4", null, null, null, null, "free", "event",
      "physical", 47.63, -122.34, "Fremont", "ok", old, old, old, fresh,
      "active",
    ],
    [
      5, "places_brand", "p5", "online", "Free online workshop",
      "https://example.com/p5", null, null, null, null, "free", "event",
      "online", null, null, null, "n/a", fresh, future, fresh, fresh,
      "active",
    ],
    [
      6, "reddit", "r6", null, "Free failed-geocode sample",
      "https://example.com/r6", null, null, null, null, "free", "food",
      "physical", null, null, "Unknown", "failed", fresh, future, fresh,
      fresh, "active",
    ],
    [
      7, "reddit", "r7", "coffee", "Free coffee duplicate",
      "https://example.com/r7", null, null, null, null, "free", "food",
      "physical", 47.621, -122.321, "Capitol Hill", "ok", fresh, future,
      fresh, fresh, "active",
    ],
    [
      8, "places_brand", "p8", "atlanta-art",
      "Free contemporary art admission",
      "https://atlantacontemporary.org/visit", "Free admission every day.",
      "All visitors.", "Visit during public hours.", "2026-07-27T00:00:00",
      "free", "event", "physical", 33.7739, -84.4059,
      "535 Means St NW, Atlanta, GA 30318", "ok", fresh, future, fresh, fresh,
      "active",
    ],
  ];

  await client.batch(
    rows.map((args) => [INSERT_DEAL, args] as [string, typeof args]),
    "write",
  );
  await client.execute({
    sql:
      "UPDATE deals SET source_tier = 'official', " +
      "verification_status = 'official', evidence_count = 1, " +
      "quality_score = 100, publication_reason = 'current_official_evidence' " +
      "WHERE id IN (2, 8)",
    args: [],
  });
  const insertRun = `
    INSERT INTO scrape_runs (
      source, started_at, finished_at, deals_found, deals_upserted,
      map_pins, geocode_failures, candidates_staged, candidates_pending,
      candidates_rejected, duration_ms, errors
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `;
  await client.batch(
    [
      [
        insertRun,
        [
          "reddit", "2026-07-16T11:59:00", "2026-07-16T12:00:00",
          4, 0, 0, 0, 4, 4, 0, 1000, null,
        ],
      ],
      [
        insertRun,
        [
          "places_brand", "2026-07-16T11:59:00",
          "2026-07-16T12:00:00", 3, 3, 1, 0, 3, 0, 0, 500, null,
        ],
      ],
    ],
    "write",
  );
  client.close();
}
