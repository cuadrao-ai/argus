import { defineConfig, devices } from "@playwright/test";

const runId = `${Date.now()}-${process.pid}`;
const port = Number(process.env.PLAYWRIGHT_PORT ?? 3100);
const externalBaseURL = process.env.PLAYWRIGHT_BASE_URL;
const reuseExistingServer =
  process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === "true";
const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH ?? "true";

export default defineConfig({
  testDir: "./e2e",
  outputDir: `./temp/playwright-results/${runId}`,
  // lastRunFile: `./temp/playwright/${runId}.last-run.json`,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  retries: 0,
  workers: 2,
  reporter: "list",
  use: {
    baseURL: externalBaseURL ?? `http://localhost:${port}`,
    trace: "on-first-retry",
  },
  webServer: externalBaseURL ? undefined : {
    command: `node ./node_modules/next/dist/bin/next dev --port ${port}`,
    port,
    reuseExistingServer,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_MOCK_AUTH: mockAuth,
      NEXT_PUBLIC_E2E_ALLOW_MOCK_SIGNUP: "true",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
