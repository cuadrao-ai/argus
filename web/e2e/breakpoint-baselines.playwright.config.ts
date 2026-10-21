import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * Visual baselines for the surfaces no queued lane is rewriting.
 *
 * A visual suite is only worth having if red means "something changed".
 * Everything here exists to remove a reason for a false red:
 *
 *  - fixture data, so no model output or live market data reaches a capture;
 *  - a fixed timezone and locale, because the allowance panel renders dates and
 *    a machine in another zone would otherwise fail every run;
 *  - `deviceScaleFactor: 1` and `scale: "css"`, so a retina laptop and a CI
 *    container rasterise at the same size;
 *  - animations disabled and the caret hidden, so a capture taken half a second
 *    later is the same bytes;
 *  - a per-pixel `threshold` plus a pixel budget measured from real runs, which
 *    absorbs font antialiasing without absorbing a moved element.
 *
 * Run and refresh with:
 *
 *   bun run test:e2e:breakpoints
 *   bun run test:e2e:breakpoints:update
 *
 * Use those scripts rather than `bunx playwright`. `bunx` resolves the latest
 * published playwright, not the version pinned in package.json, so it would
 * quietly re-render every baseline the day a new minor ships. `bun run` uses
 * node_modules/.bin, which is the pinned one.
 *
 * Baselines are platform-suffixed, so a run on one OS never argues with another
 * OS's committed set. The committed set is darwin. CI is ubuntu and does not
 * run this spec; before adding it, generate the linux set from the repo root in
 * the image matching the pinned version:
 *
 *   docker run --rm --add-host=host.docker.internal:host-gateway -v "$PWD":/w \
 *     -w /w/web -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3195 \
 *     mcr.microsoft.com/playwright:v1.59.1-noble \
 *     node ./node_modules/@playwright/test/cli.js \
 *     -c e2e/breakpoint-baselines.playwright.config.ts --update-snapshots
 *
 * That path is not proven end to end: auth capture cleanly, but the
 * settings walk needs a /chat boot and timed out against a host-side dev server.
 * Running the dev server inside the container instead is the likely fix, and is
 * work for whoever wires this into CI.
 */

const repositoryRoot = path.resolve(__dirname, "../..");
const port = Number(process.env.ARGUS_BREAKPOINT_BASELINE_PORT ?? 3195);
/* Set when the browser runs in the linux container and the dev server runs on
   the host, which is how the committed linux baselines are produced. */
const externalBaseURL = process.env.PLAYWRIGHT_BASE_URL;
const appOrigin = externalBaseURL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: path.join(repositoryRoot, "web/e2e"),
  testMatch: "breakpoint-baselines.spec.ts",
  outputDir: path.join(repositoryRoot, "temp/breakpoint-baselines-playwright"),
  snapshotDir: path.join(repositoryRoot, "web/e2e/__screenshots__"),
  snapshotPathTemplate:
    "{snapshotDir}/{platform}/{arg}{ext}",
  timeout: 90_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      scale: "css",
      /*
       * Calibrated, not guessed. With the dev badge hidden, all 74 captures
       * pass at `maxDiffPixels: 0`, so run-to-run noise on the reference
       * machine is zero and this budget is headroom for a different machine
       * rather than cover for known drift. Re-measure the same way after
       * changing anything about how captures are taken.
       *
       * It replaced `maxDiffPixelRatio: 0.01`, which sounded strict and was
       * not: one percent of a 390x844 viewport is about 3,300 pixels, and a
       * 40x40 element was in fact removed from every capture without the suite
       * going red. 100 still catches anything roughly 10x10 and larger. An
       * absolute budget also scales the right way, since a small settings panel
       * gets proportionally stricter than a full page.
       */
      threshold: 0.2,
      maxDiffPixels: 100,
    },
  },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: appOrigin,
    trace: "off",
    video: "off",
    timezoneId: "UTC",
    locale: "en-US",
    deviceScaleFactor: 1,
  },
  webServer: externalBaseURL ? undefined : {
    command: `node ./node_modules/next/dist/bin/next dev --port ${port}`,
    cwd: path.join(repositoryRoot, "web"),
    url: appOrigin,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "ignore",
    stderr: "pipe",
    env: {
      NEXT_PUBLIC_MOCK_AUTH: "true",
      NEXT_PUBLIC_ENABLE_SPANISH: "true",
      NEXT_PUBLIC_GUEST_ACCESS_ENABLED: "true",
      NEXT_PUBLIC_ARGUS_API_URL: "http://127.0.0.1:3999/api/v1",
      NEXT_PUBLIC_SUPABASE_URL: "https://test-project.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: "test-anon-key",
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
