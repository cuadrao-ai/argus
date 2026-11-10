import { defineConfig } from "@playwright/test";

const port = 3187;
export default defineConfig({
  testDir: ".",
  testMatch: "account-avatar.spec.ts",
  outputDir: "../temp/account-avatar-results",
  workers: 1,
  retries: 0,
  use: { baseURL: `http://127.0.0.1:${port}` },
  webServer: {
    command: `bun run start --hostname 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    env: { NEXT_TELEMETRY_DISABLED: "1", NEXT_PUBLIC_MOCK_AUTH: "true", NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true" },
  },
});
