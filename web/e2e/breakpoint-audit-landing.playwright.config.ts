import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * The landing surface only exists without an established session. Mock auth
 * sends `/` straight to `/chat`, so the guest entry and the signed-out auth
 * screens need their own server with mock auth off.
 */

const repositoryRoot = path.resolve(__dirname, "../..");
const port = Number(process.env.ARGUS_BREAKPOINT_LANDING_PORT ?? 3194);
const appOrigin = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: path.join(repositoryRoot, "web/e2e"),
  testMatch: "breakpoint-audit-landing.spec.ts",
  outputDir: path.join(repositoryRoot, "temp/breakpoint-landing-playwright"),
  timeout: 90_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: appOrigin, trace: "off", video: "off", screenshot: "off" },
  webServer: {
    command: `node ./node_modules/next/dist/bin/next dev --port ${port}`,
    cwd: path.join(repositoryRoot, "web"),
    url: appOrigin,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "false",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_GUEST_ACCESS_ENABLED: "true",
      NEXT_PUBLIC_CUADRAO_API_URL: "http://127.0.0.1:3999/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "https://test-project.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
