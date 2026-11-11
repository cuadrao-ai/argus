import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const repositoryRoot = path.resolve(__dirname, "../..");
const port = Number(process.env.ARGUS_ACCESS_REQUEST_TEST_PORT ?? 3193);
const appOrigin = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: path.join(repositoryRoot, "web/e2e"),
  testMatch: "public-alpha-access-request.spec.ts",
  outputDir: path.join(
    repositoryRoot,
    "temp/public-alpha-access-request-playwright",
  ),
  timeout: 90_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: appOrigin,
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  webServer: {
    command: `node ./node_modules/next/dist/bin/next dev --port ${port}`,
    cwd: path.join(repositoryRoot, "web"),
    url: appOrigin,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_GUEST_ACCESS_ENABLED: "false",
      NEXT_PUBLIC_CUADRAO_API_URL: "http://127.0.0.1:3999/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "https://test-project.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
    },
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
});
