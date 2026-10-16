import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: ".", testMatch: "business-personal-menu.spec.ts", workers: 1, retries: 0,
  timeout: 30_000, expect: { timeout: 7000 }, reporter: "list",
  outputDir: "../temp/item7-playwright",
  use: { baseURL: "http://localhost:3197" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: { command: "bun run start --port 3197", port: 3197, reuseExistingServer: true, timeout: 30_000 },
});
