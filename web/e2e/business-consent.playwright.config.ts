import { defineConfig } from "@playwright/test";
import path from "node:path";

const port = Number(process.env.PLAYWRIGHT_PORT ?? 3198);

export default defineConfig({
  testDir: ".",
  testMatch: "business-consent.spec.ts",
  outputDir: "../temp/consent-results",
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: {
    baseURL: `http://localhost:${port}`,
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
  },
  webServer: {
    command: `node node_modules/next/dist/bin/next dev --webpack --port ${port}`,
    cwd: path.resolve(__dirname, ".."),
    port,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true",
      NEXT_PUBLIC_ARGUS_API_URL: `http://localhost:${port}/api/v1`,
      NEXT_PUBLIC_SUPABASE_URL: `http://localhost:${port}`,
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "synthetic",
    },
  },
});
