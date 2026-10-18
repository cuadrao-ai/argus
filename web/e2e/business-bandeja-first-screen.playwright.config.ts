import { defineConfig } from "@playwright/test";
import path from "node:path";

export default defineConfig({
  testDir: ".",
  testMatch: "business-bandeja-first-screen.spec.ts",
  outputDir: "../temp/bandeja-first-screen-results",
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: { baseURL: "http://localhost:3196" },
  webServer: {
    command: "node node_modules/next/dist/bin/next dev --webpack --port 3196",
    cwd: path.resolve(__dirname, ".."),
    port: 3196,
    timeout: 120_000,
    env: {
      BANDEJA_FIRST_SCREEN: "1",
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_CUADRAO_BUSINESS_PILOT_ENABLED: "true",
      NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true",
      NEXT_PUBLIC_ARGUS_API_URL: "http://localhost:3196/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "http://localhost:3196",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "synthetic",
    },
  },
});