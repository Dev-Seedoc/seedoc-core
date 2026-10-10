import { existsSync } from "node:fs";
import { loadEnvFile } from "node:process";
import { fileURLToPath, URL } from "node:url";

import { defineConfig, devices } from "@playwright/test";

// Test-only values (NAMING §10): apps/web/e2e/.env, git-ignored. Variables already set in the environment win (CI).
const envFile = fileURLToPath(new URL("./e2e/.env", import.meta.url));
if (existsSync(envFile)) {
  loadEnvFile(envFile);
}

// Runs against the local stack (`make up`, `make migrate`, `make dev`), not staging: staging has no Mailpit.
export default defineConfig({
  testDir: "./e2e",
  // One end-to-end flow that builds on its own data; parallel runs would only fight over the dev server.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5173",
    locale: "de-DE",
    timezoneId: "Europe/Berlin",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
