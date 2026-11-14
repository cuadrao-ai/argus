import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.ISSUE_334_PLAYWRIGHT_PORT ?? 3101);

export default defineConfig({
  testDir: ".",
  testMatch: "issue-334-omnisearch-shortcut-legend.spec.ts",
  outputDir: "../temp/issue-334-browser-matrix-results",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: { baseURL: `http://localhost:${port}` },
  webServer: {
    command: `node ./node_modules/next/dist/bin/next dev --port ${port}`,
    cwd: "..",
    port,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_DIST_DIR: ".next-issue334-playwright",
    },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
