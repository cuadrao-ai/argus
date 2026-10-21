import path from "node:path";
import { defineConfig } from "@playwright/test";
const port = 3196;
const origin = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: __dirname, testMatch: "auth-account-transition.spec.ts",
  outputDir: "../temp/urgent06e/browser", retries: 0, workers: 1, timeout: 30000,
  use: { baseURL: origin, screenshot: "only-on-failure" },
  webServer: [{ command: "bun e2e/support/auth-account-transition-server.mjs", cwd: path.resolve(__dirname, ".."), url: "http://127.0.0.1:3197/health", reuseExistingServer: false }, {
    command: `bun run dev --port ${port}`,
    cwd: path.resolve(__dirname, ".."), url: origin, reuseExistingServer: false,
    env: { NEXT_PUBLIC_MOCK_AUTH: "false", NEXT_PUBLIC_GUEST_ACCESS_ENABLED: "false", NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true", NEXT_PUBLIC_CUADRAO_API_URL: `${origin}/api/v1`, NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:3197", NEXT_PUBLIC_SUPABASE_ANON_KEY: "local-fixture-anon" },
  }],
});
