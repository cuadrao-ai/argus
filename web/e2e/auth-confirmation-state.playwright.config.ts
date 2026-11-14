import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const repositoryRoot = path.resolve(__dirname, "../..");
const port = Number(process.env.ARGUS_AUTH_CONFIRMATION_TEST_PORT ?? 3192);
const appOrigin = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: path.join(repositoryRoot, "web/e2e"),
  testMatch: "auth-confirmation-state.spec.ts",
  outputDir: path.join(
    repositoryRoot,
    "temp/auth-confirmation-playwright",
  ),
  timeout: 30_000,
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
      NEXT_PUBLIC_MOCK_AUTH: "false",
      NEXT_PUBLIC_GUEST_ACCESS_ENABLED: "false",
      NEXT_PUBLIC_CUADRAO_API_URL: "http://127.0.0.1:3999/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: appOrigin,
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
