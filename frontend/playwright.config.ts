import { defineConfig, devices } from "@playwright/test"

/**
 * Run Playwright tests against a locally-running backend in test mode.
 *
 * The backend must be started separately with TEST_MODE=1 so the
 * /test/login route is registered. We assume the backend serves the
 * built frontend bundle at the root.
 *
 *   TEST_MODE=1 uv run uvicorn podking.main:app --host 127.0.0.1 --port 8001
 *   cd frontend && npm run e2e
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false, // serial keeps DB state predictable
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "list" : "line",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8001",
    trace: "on-first-retry",
    permissions: ["clipboard-read", "clipboard-write"],
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
})
