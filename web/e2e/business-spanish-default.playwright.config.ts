import { defineConfig } from "@playwright/test";
import path from "node:path";

export default defineConfig({
  testDir: ".",
  testMatch: "business-spanish-default.spec.ts",
  outputDir: "/tmp/business-es419-results",
  workers: 1,
  retries: 0,
  timeout: 90_000,
  use: {
    baseURL: "http://127.0.0.1:3198",
    locale: "en-US",
    channel: "chrome",
    viewport: { width: 1280, height: 900 },
  },
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --webpack --port 3198",
    cwd: path.resolve(__dirname, ".."),
    port: 3198,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true",
      NEXT_PUBLIC_ARGUS_API_URL: "http://127.0.0.1:3198/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:3198",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "synthetic",
    },
  },
});
