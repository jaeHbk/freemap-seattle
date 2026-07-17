import path from "node:path";

export const E2E_DATABASE_PATH = path.resolve(
  process.cwd(),
  "e2e/playwright.db",
);
export const E2E_DATABASE_URL = `file:${E2E_DATABASE_PATH}`;
