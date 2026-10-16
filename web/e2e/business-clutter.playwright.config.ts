import { defineConfig } from "@playwright/test";
import path from "node:path";

export default defineConfig({
  testDir: ".",
  testMatch: "business-clutter.spec.ts",
  outputDir: "../temp/clutter-results",
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: { baseURL: "http://localhost:3195" },
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --webpack --port 3195",
    cwd: path.resolve(__dirname, ".."),
    port: 3195,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_CUADRAO_BUSINESS_PILOT_ENABLED: "true",
      NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true",
      NEXT_PUBLIC_ARGUS_API_URL: "http://localhost:3195/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "http://localhost:3195",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "synthetic",
    },
  },
});
