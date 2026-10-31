import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "../e2e/support/breakpoint-fixture";

const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:4515";
assert.equal(new URL(baseURL).hostname, "127.0.0.1");
const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/startup-design-evidence");
mkdirSync(output, { recursive: true });

function gate() {
  let release!: () => void;
  const promise = new Promise<void>((done) => { release = done; });
  return { promise, release };
}

const browser = await chromium.launch({ headless: true });
const captures: { file: string; sha256: string; language: string; theme: string; width: number; height: number; state: string }[] = [];
try {
  for (const language of ["es-419", "en"] as const) {
    for (const theme of ["light", "dark"] as const) {
      for (const [width, height] of [[320, 844], [390, 844], [844, 390], [1440, 900]]) {
        const page = await browser.newPage({ viewport: { width, height }, colorScheme: theme });
        const directory = gate();
        const consent = gate();
        const source = createFixtureBusinessDataSource({ chatAvailable: false });
        const unexpected: string[] = [];
        const errors: string[] = [];
        let directoryReads = 0;
        let consentReads = 0;
        let scenario: "slow" | "fast" | "consent-exit" | "error-exit" = "slow";
        page.on("pageerror", (error) => errors.push(error.message));
        await installBreakpointFixture(page, { language, theme, emptyChat: true });
        await page.route("**/api/v1/business/**", async (route) => {
          const url = new URL(route.request().url());
          const path = url.pathname.split("/business/")[1] ?? "";
          if (path === "spaces") {
            if (scenario === "error-exit") return route.fulfill({ status: 503, json: { code: "synthetic_unavailable" } });
            directoryReads += 1;
            if (scenario === "slow" && directoryReads === 1) await directory.promise;
            return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1), closed_spaces: [] } });
          }
          if (path === "consent") {
            consentReads += 1;
            if (scenario === "slow") await consent.promise;
            if (scenario === "consent-exit") return route.fulfill({ json: { version: "synthetic", accepted_at: null } });
            return fulfillAcceptedBusinessConsent(route);
          }
          if (path === "workspace") return route.fulfill({ json: await source.workspace() });
          if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
          if (path === "space/name-prompt") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba", name_required: false, name_prompt_seen: true, show_prompt: false } });
          if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
          if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, needs_attention_count: 0, confirmed_count: 0, dismissed_count: 0 } } });
          if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
          if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
          if (path === "email/inbox" && route.request().method() === "GET") return route.fulfill({ json: { groups: [{ id: "remitentes_nuevos", items: [] }, { id: "bandeja", items: [] }] } });
          if (path === "captures" || path === "email/deliveries") return route.fulfill({ json: { items: [] } });
          return route.fulfill({ status: 404, json: { code: "synthetic_unmapped" } });
        });
        await page.route("**/*", (route) => {
          const url = new URL(route.request().url());
          if (url.origin === new URL(baseURL).origin) return route.fallback();
          unexpected.push(`${route.request().method()} ${url.pathname}`);
          return route.abort();
        });
        const prefix = `${language}-${theme}-${width}x${height}`;
        const capture = async (state: string) => {
          const file = `${prefix}-${state}.png`;
          await page.evaluate((label) => {
            const mark = document.createElement("div");
            mark.textContent = label;
            mark.dataset.startupEvidenceMark = "true";
            mark.setAttribute("aria-hidden", "true");
            mark.style.cssText = "position:fixed;right:8px;bottom:8px;z-index:99999;background:#ffda80;color:#172b26;padding:4px 8px;border-radius:4px;font:bold 11px sans-serif;pointer-events:none";
            document.body.append(mark);
          }, `SYNTHETIC STARTUP ${head.slice(0, 7)}`);
          const bytes = await page.screenshot({ path: resolve(output, file), fullPage: true, scale: "css" });
          await page.locator('[data-startup-evidence-mark="true"]').evaluate((node) => node.remove());
          captures.push({ file, sha256: createHash("sha256").update(bytes).digest("hex"), language, theme, width, height, state });
        };
        try {
          await page.goto(`${baseURL}/biz`, { waitUntil: "domcontentloaded" });
          const loader = page.getByTestId("fullscreen-loading");
          await expect(loader).toHaveCount(1);
          await expect(loader.getByRole("status")).toHaveText(language === "es-419" ? "Cargando..." : "Loading...");
          await expect(loader.getByRole("status")).toHaveAttribute("aria-live", "polite");
          const loaderNode = await loader.elementHandle();
          assert.ok(loaderNode);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
          assert.equal(await page.evaluate(() => document.activeElement?.closest("[hidden]") !== null), false);
          await capture("loading");
          directory.release();
          await expect.poll(() => consentReads).toBeGreaterThan(0);
          assert.equal(await loaderNode.evaluate((node) => node.isConnected), true, `${prefix} kept one loader through consent`);
          consent.release();
          await expect(page.locator("#business-overview-title")).toBeVisible();
          await expect(loader).toHaveCount(0);
          await expect(page.locator('[data-testid="fullscreen-loading"] [role="status"]')).toHaveCount(0);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
          await capture("home");
          if (language === "es-419" && theme === "light" && width === 390) {
            scenario = "fast";
            await page.reload({ waitUntil: "domcontentloaded" });
            await expect(page.locator("#business-overview-title")).toBeVisible();
            await page.waitForTimeout(350);
            await expect(loader).toHaveCount(0);
            await capture("fast-home");
            scenario = "consent-exit";
            await page.reload({ waitUntil: "domcontentloaded" });
            await expect(page.getByTestId("business-consent-screen")).toBeVisible();
            await expect(loader).toHaveCount(0);
            await capture("consent-exit");
            scenario = "error-exit";
            await page.reload({ waitUntil: "domcontentloaded" });
            await expect(page.getByRole("alert").first()).toBeVisible();
            await expect(loader).toHaveCount(0);
            await capture("error-exit");
          }
          assert.deepEqual(unexpected, [], `${prefix} used local requests only`);
          assert.deepEqual(errors, [], `${prefix} had no page errors`);
        } finally {
          directory.release();
          consent.release();
          await page.close();
        }
      }
    }
  }
} finally {
  await browser.close();
  writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, kind: "local synthetic startup", captures }, null, 2));
}
console.log(`Captured ${captures.length} synthetic startup screenshots at ${head}`);
