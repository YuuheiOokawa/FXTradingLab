import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config. Assumes Postgres/Redis/backend API/worker/frontend dev server
 * are already running (see docs/18_E2E_TESTING.md) — this does NOT spin up
 * the stack itself, since the backend/worker are separate processes outside
 * npm's reach.
 *
 * PLAYWRIGHT_CHROMIUM_PATH lets a sandboxed dev environment point at a
 * pre-installed browser instead of the default `playwright install` cache
 * location; unset (the CI/local default) leaves Playwright's own resolution
 * alone.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
          ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
          : {}),
      },
    },
  ],
});
