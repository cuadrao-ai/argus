import path from "node:path";
import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3217";

export default defineConfig({
  testDir: ".",
  testMatch: ["fullscreen-loading.spec.ts", "business-loading.spec.ts"],
  outputDir: "../../temp/fullscreen-loading/playwright",
  workers: 1,
  retries: 0,
  timeout: 90_000,
  use: { baseURL, trace: "off", viewport: { width: 1280, height: 900 } },
  webServer: process.env.PLAYWRIGHT_BASE_URL ? undefined : {
    command: "bun run dev --hostname 127.0.0.1 --port 3217",
    cwd: path.resolve(__dirname, ".."),
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_ARGUS_API_URL: "http://127.0.0.1:3999/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54321",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "local-fixture-anon",
    },
  },
});
