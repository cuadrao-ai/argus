import path from "node:path";
import { defineConfig } from "@playwright/test";

const repositoryRoot = path.resolve(__dirname, "../..");
const port = Number(process.env.ARGUS_GUEST_CAPTCHA_UX_TEST_PORT ?? 3011);
const appOrigin = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: path.join(repositoryRoot, "web/e2e"),
  testMatch: "guest-auth-captcha-ux.spec.ts",
  outputDir: path.join(
    repositoryRoot,
    "temp/guest-auth-captcha-ux-playwright",
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
    headless: true,
    viewport: { width: 1422, height: 800 },
    trace: "off",
    video: "off",
    screenshot: "off",
  },
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
      NEXT_PUBLIC_GUEST_ACCESS_ENABLED: "false",
      NEXT_PUBLIC_ARGUS_API_URL: "http://127.0.0.1:3999/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "https://test-project.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
      NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN: "",
      NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY: "1x00000000000000000000BB",
      NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY: "1x00000000000000000000BB",
    },
  },
});
