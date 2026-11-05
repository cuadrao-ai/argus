import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "native-captcha.spec.ts",
  workers: 1,
  use: { baseURL: "http://127.0.0.1:58515", browserName: "chromium" },
  webServer: {
    command: "bun run start --hostname 127.0.0.1 --port 58515",
    url: "http://127.0.0.1:58515/auth/native-captcha",
    reuseExistingServer: false,
    cwd: process.cwd(),
  },
});
