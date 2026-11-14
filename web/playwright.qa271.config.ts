import { defineConfig, devices } from "@playwright/test";

// Real-auth issue-271 modeled-cost journey config. Targets the actual Argus app
// on the documented local origin (http://localhost:3000) with mock auth
// disabled. The Argus API must already run on 127.0.0.1:8000 in QA mode with a
// real interpreter (see scripts/qa/README.md for the local stack sequence).
const port = 3000;

export default defineConfig({
  testDir: "./e2e/qa-271",
  outputDir: "../temp/qa-evidence-271/test-results",
  timeout: 600_000,
  expect: { timeout: 15_000 },
  // One continuous conversation; order matters.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    [
      "html",
      { outputFolder: "../temp/qa-evidence-271/html-report", open: "never" },
    ],
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
