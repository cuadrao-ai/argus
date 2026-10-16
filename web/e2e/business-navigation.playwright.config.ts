import { defineConfig } from "@playwright/test";
import path from "node:path";

const production = process.env.CUADRAO_NAV_PRODUCTION === "true";

export default defineConfig({
  testDir: ".",
  testMatch: production ? "business-navigation-focus.spec.ts" : "business-navigation-shortcuts.spec.ts",
  outputDir: "../temp/navigation-results",
  workers: 1,
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "firefox", use: { browserName: "firefox" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  retries: 0,
  timeout: 60_000,
  use: { baseURL: "http://localhost:3196" },
  webServer: {
    command: production ? "node node_modules/next/dist/bin/next start --port 3196" : "node node_modules/next/dist/bin/next dev --webpack --port 3196",
    cwd: path.resolve(__dirname, ".."),
    port: 3196,
    timeout: 120_000,
    env: {
      NEXT_DIST_DIR: production ? ".next" : ".next-navigation",
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
