import path from "node:path";
import os from "node:os";
import { defineConfig } from "@playwright/test";

const repositoryRoot = path.resolve(__dirname, "../..");
const port = Number(process.env.ARGUS_ISSUE_340_TEST_PORT ?? 3012);
const appOrigin = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: path.join(repositoryRoot, "web/e2e"),
  testMatch: "issue-340-guest-dossier-conversion-gate.spec.ts",
  outputDir: path.join(os.tmpdir(), "argus-issue-340-playwright"),
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: appOrigin,
    headless: true,
    trace: "retain-on-failure",
    video: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop-chromium",
      use: { viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "mobile-chromium",
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: `bun run build && bun run start -- --hostname 127.0.0.1 --port ${port}`,
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
      NEXT_PUBLIC_ARGUS_API_URL: "http://127.0.0.1:3999/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "https://test-project.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
      NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN: "argus-local-browser-qa",
      NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY: "",
      NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY: "",
    },
  },
});
