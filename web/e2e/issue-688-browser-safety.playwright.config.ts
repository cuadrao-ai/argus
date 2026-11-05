import { defineConfig, devices } from '@playwright/test';
const port = Number(process.env.PLAYWRIGHT_PORT ?? 3688);
export default defineConfig({
  testDir: '.', testMatch: 'issue-688-browser-safety.spec.ts', workers: 1,
  timeout: 60000, expect: { timeout: 15000 }, reporter: 'list',
  outputDir: '../temp/issue-688',
  use: { baseURL: `http://127.0.0.1:${port}`, ...devices['Desktop Chrome'] },
  webServer: [{ command: 'node e2e/issue-688-browser-safety-server.mjs', cwd: process.cwd(), url: 'http://127.0.0.1:5688/health', reuseExistingServer: false }, { cwd: process.cwd(), command: `node node_modules/next/dist/bin/next dev --webpack --port ${port}`, url: `http://127.0.0.1:${port}`, reuseExistingServer: false, timeout: 120000,
    env: { NEXT_DIST_DIR: '.next-688', NEXT_PUBLIC_MOCK_AUTH: 'false', NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:5688', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'local-fixture-only', NEXT_PUBLIC_ARGUS_API_URL: 'http://127.0.0.1:5688/api/v1', NEXT_PUBLIC_ENABLE_SPANISH: 'true', NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED: 'true' } }],
});
