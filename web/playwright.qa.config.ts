import { defineConfig, devices } from "@playwright/test";

// Real-auth issue-248 QA config. Targets the actual Argus app on the exact
// documented local origin (http://localhost:3000) with mock auth disabled.
// The Argus API must already run on 127.0.0.1:8000 (scripts/qa/run-local-auth-qa.sh).
const port = 3000;

export default defineConfig({
  testDir: "./e2e/qa-248",
  outputDir: "../temp/qa-evidence-248/test-results",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  // Journeys mutate one shared QA identity's password and sessions; order matters.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "../temp/qa-evidence-248/html-report", open: "never" }],
  ],
  globalSetup: "./e2e/qa-248/global-setup.ts",
  use: {
    baseURL: `http://localhost:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `node ./node_modules/next/dist/bin/next dev --port ${port}`,
    port,
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "false",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
