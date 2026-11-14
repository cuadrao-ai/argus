import { defineConfig } from "@playwright/test";
import path from "node:path";

export default defineConfig({
  testDir: ".",
  testMatch: "business-spanish-default.spec.ts",
  outputDir: "../temp/business-es419-results",
  workers: 1,
  retries: 0,
  timeout: 90_000,
  use: {
    baseURL: "http://127.0.0.1:3198",
    locale: "en-US",
    viewport: { width: 1280, height: 900 },
  },
  webServer: {
    // Production mode exercises account saves instead of the development-only language preview.
    command: "bun run build && bun run start --hostname 127.0.0.1 --port 3198",
    cwd: path.resolve(__dirname, ".."),
    port: 3198,
    timeout: 180_000,
    env: {
      NEXT_TELEMETRY_DISABLED: "1",
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true",
      NEXT_PUBLIC_CUADRAO_API_URL: "http://127.0.0.1:3198/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:3198",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "synthetic",
    },
  },
});
