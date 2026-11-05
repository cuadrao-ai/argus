import { defineConfig, devices } from "@playwright/test";

const runId = `${Date.now()}-${process.pid}`;
const port = Number(process.env.PLAYWRIGHT_PORT ?? 3100);
const externalBaseURL = process.env.PLAYWRIGHT_BASE_URL;
const reuseExistingServer =
  process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === "true";
const mockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH ?? "true";
// The specs skip by this flag, so the server it starts must be built with the same value.
const businessPilot = process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED ?? "false";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: "**/guest-auth-captcha-ux.spec.ts",
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
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED: "true",
      NEXT_PUBLIC_E2E_ALLOW_MOCK_SIGNUP: "true",
      NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: businessPilot,
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
