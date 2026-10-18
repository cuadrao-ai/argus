import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

import { MOCK_PORT, SITE_PORT, PUBLIC_PORT } from "./e2e/ports";

const providerEnv = {
  NODE_OPTIONS: `--require=${resolve("e2e/waitlist-fetch-preload.cjs")}`,
  MARKETING_WAITLIST_FROM: "Cuadrao <lista@cuadrao.ai>",
  MARKETING_POSTAL_ADDRESS: "Cuadrao LLC, 1209 Mountain Road Pl NE Ste N, Albuquerque NM 87110, EE. UU.",
  CUADRAO_WAITLIST_ORIGIN: "https://cuadrao.example.test",
  CUADRAO_WAITLIST_TURNSTILE_SECRET: "fixture-secret",
  RESEND_API_KEY: "test-resend-key",
  RESEND_API_URL: `http://127.0.0.1:${MOCK_PORT}`,
  CUADRAO_INQUIRY_FROM: "Cuadrao <website@notify.example.test>",
  CUADRAO_INQUIRY_TO: "inbox@example.test",
  SUPABASE_URL: `http://127.0.0.1:${MOCK_PORT}`,
  SUPABASE_SERVICE_ROLE_KEY: "test-service-key",
};

const start = (port: number, env: Record<string, string> = {}) => ({
  command: `bunx next start -p ${port}`,
  url: `http://127.0.0.1:${port}/api/health`,
  reuseExistingServer: !process.env.CI,
  env: { ...providerEnv, ...env },
});

// The site is started from an existing production build: run `bun run build` first.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${SITE_PORT}`, trace: "retain-on-failure" },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: "node e2e/mock-providers.mjs",
      env: { MOCK_PROVIDER_PORT: String(MOCK_PORT) },
      url: `http://127.0.0.1:${MOCK_PORT}/__state`,
      reuseExistingServer: !process.env.CI,
    },
    start(SITE_PORT),
    start(PUBLIC_PORT, { CUADRAO_SITE_INDEXING: "public" }),
  ],
});
