import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect, type Page } from "@playwright/test";

const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/home-checkpoint-integration/evidence");
const baseURL = "http://127.0.0.1:4417";
const fixtureURL = "http://127.0.0.1:4418";
assert.equal(new URL(baseURL).hostname, "127.0.0.1");
assert.equal(new URL(fixtureURL).hostname, "127.0.0.1");
mkdirSync(output, { recursive: true });

type Fixture = { language: "es-419" | "en"; monthClose?: "normal" | "zero" | "error" | "refused"; inbox?: "normal" | "zero" | "failed" | "refused"; earliest?: string };
type Capture = { file: string; sha256: string; bytes: number; width: number; height: number; innerWidth: number; clientWidth: number; scrollWidth: number; language: string; theme: string; state: string };
const captures: Capture[] = [];
const checks: string[] = [];
const errors: string[] = [];

async function fixture(value: Fixture) {
  const response = await fetch(`${fixtureURL}/__preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario: "fast", ...value }),
  });
  assert.equal(response.status, 200);
}

async function capture(page: Page, name: string, language: string, theme: string) {
  const viewport = page.viewportSize();
  assert.ok(viewport);
  const measure = await page.evaluate(() => ({
    innerWidth,
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert.equal(measure.innerWidth, viewport.width, `${name}: CSS viewport`);
  assert.equal(measure.clientWidth, viewport.width, `${name}: document width`);
  assert.ok(measure.scrollWidth <= viewport.width, `${name}: horizontal overflow ${measure.scrollWidth} > ${viewport.width}`);
  const file = `${name}.png`;
  const bytes = await page.screenshot({ path: resolve(output, file), fullPage: true, type: "png", scale: "css" });
  assert.equal(bytes.subarray(0, 8).toString("hex"), "89504e470d0a1a0a", `${name}: genuine PNG`);
  captures.push({ file, sha256: createHash("sha256").update(bytes).digest("hex"), bytes: bytes.length,
    width: viewport.width, height: viewport.height, ...measure, language, theme, state: name });
}

const browser = await chromium.launch({ headless: true });
try {
  const matrix = [
    { language: "es-419" as const, theme: "light", width: 390, height: 844, mobile: true },
    { language: "es-419" as const, theme: "light", width: 820, height: 900, mobile: false },
    { language: "es-419" as const, theme: "light", width: 1440, height: 900, mobile: false },
    { language: "es-419" as const, theme: "dark", width: 390, height: 844, mobile: true },
    { language: "es-419" as const, theme: "dark", width: 1440, height: 900, mobile: false },
    { language: "en" as const, theme: "light", width: 390, height: 844, mobile: true },
    { language: "en" as const, theme: "light", width: 1440, height: 900, mobile: false },
    { language: "en" as const, theme: "dark", width: 390, height: 844, mobile: true },
  ];
  for (const sample of matrix) {
    await fixture({ language: sample.language });
    const context = await browser.newContext({ viewport: { width: sample.width, height: sample.height },
      isMobile: sample.mobile, deviceScaleFactor: 1, colorScheme: sample.theme as "light" | "dark" });
    await context.addInitScript(([language, theme]) => {
      localStorage.setItem("i18nextLng", language);
      localStorage.setItem("argus-theme", theme);
      localStorage.setItem("argus:sidebar_mode", "expanded");
    }, [sample.language, sample.theme]);
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(`${sample.language}-${sample.theme}-${sample.width}: ${error.message}`));
    await page.goto(`${baseURL}/biz`, { waitUntil: "domcontentloaded" });
    await expect(page.locator("#business-overview-title")).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId("month-close-checklist")).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId("month-close-task-review")).toBeVisible({ timeout: 30000 });
    await expect(page.locator('iframe[src^="/design-workspace/card"]')).toHaveCount(1);
    await expect(page.frameLocator('iframe[src^="/design-workspace/card"]').locator(".setup")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", sample.language === "es-419" ? "es" : "en");
    await expect(page.locator("html")).toHaveClass(sample.theme === "dark" ? /dark/ : /^(?!.*dark)/);
    const key = `${sample.language}-${sample.theme}-${sample.width}x${sample.height}`;
    await capture(page, `${key}-home`, sample.language, sample.theme);
    if (sample.width === 390 && sample.language === "es-419" && sample.theme === "light") {
      await page.getByTestId("month-close-itbis").scrollIntoViewIfNeeded();
      await capture(page, `${key}-figures`, sample.language, sample.theme);
      await page.getByTestId("month-close-month").scrollIntoViewIfNeeded();
    }
    checks.push(`${key}: actual /biz Home and development-only guide visible without horizontal overflow`);
    if (sample.language === "es-419" && sample.theme === "light" && sample.width === 390) {
      const button = page.getByTestId("month-close-month");
      await button.click();
      const list = page.getByTestId("month-close-month-picker");
      await expect(list).toBeVisible();
      const months = await list.locator("[data-month]").evaluateAll((nodes) => nodes.map((node) => (node as HTMLElement).dataset.month ?? ""));
      assert.ok(months.length >= 1);
      const current = new Date().toISOString().slice(0, 7);
      assert.ok(months.every((month) => month <= current), `future month offered: ${months.join(",")}`);
      await capture(page, `${key}-month-picker`, sample.language, sample.theme);
      await list.press("End");
      await list.press("Home");
      await list.press("Escape");
      await expect(list).toHaveCount(0);
      await expect(button).toBeFocused();
      checks.push(`month picker ${months.join(",")} has no future row and Escape restores focus`);
      if (months.length > 1) {
        await button.click();
        await page.getByTestId("month-close-month-picker").locator(`[data-month="${months[0]}"]`).click();
        await expect(page.getByTestId("month-close-month-prev")).toBeDisabled();
        await capture(page, `${key}-supported-history`, sample.language, sample.theme);
        checks.push(`oldest supported month ${months[0]} is selectable; previous arrow is disabled`);
      }
    }
    if (sample.language === "es-419" && sample.theme === "light" && sample.width === 1440) {
      const rail = page.locator('aside:has([data-testid="business-sidebar-nav"])');
      const expanded = await rail.boundingBox();
      await page.getByTestId("sidebar-rail-toggle").first().click();
      await expect(page.getByTestId("sidebar-rail-toggle").first()).toHaveAttribute("aria-expanded", "false");
      await page.waitForTimeout(250);
      const icons = await rail.boundingBox();
      assert.ok(expanded && icons && Math.abs(expanded.width - 240) < 2 && Math.abs(icons.width - 64) < 2);
      await capture(page, `${key}-icons-rail`, sample.language, sample.theme);
      checks.push(`shared shell rail changes from ${expanded.width}px to ${icons.width}px without moving Home offscreen`);
    }
    await context.close();
  }
  for (const [state, settings] of [
    ["zero", { monthClose: "zero", inbox: "zero" }],
    ["month-error", { monthClose: "error", inbox: "normal" }],
    ["count-failed", { monthClose: "zero", inbox: "failed" }],
    ["count-refused", { monthClose: "zero", inbox: "refused" }],
  ] as const) {
    await fixture({ language: "es-419", ...settings });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 1, colorScheme: "light" });
    await context.addInitScript(() => { localStorage.setItem("i18nextLng", "es-419"); localStorage.setItem("argus-theme", "light"); });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(`${state}: ${error.message}`));
    await page.goto(`${baseURL}/biz`, { waitUntil: "domcontentloaded" });
    await expect(page.locator("#business-overview-title")).toBeVisible({ timeout: 30000 });
    if (state === "zero") {
      await expect(page.getByTestId("month-close-checklist-ready")).toBeVisible({ timeout: 30000 });
      await expect(page.getByTestId("month-close-close")).toBeVisible();
      await page.getByTestId("month-close-close").scrollIntoViewIfNeeded();
      checks.push("known zero receipts allows the close action in the synthetic fixture");
    } else if (state === "month-error") {
      await expect(page.getByTestId("month-close-error")).toBeVisible({ timeout: 30000 });
      await expect(page.getByTestId("month-close-close")).toHaveCount(0);
      await page.getByTestId("month-close-error").scrollIntoViewIfNeeded();
      checks.push("month read error blocks close");
    } else {
      await expect(page.getByTestId("inicio-error")).toBeVisible({ timeout: 30000 });
      await expect(page.getByTestId("month-close-close")).toHaveCount(0);
      await page.getByTestId("inicio-error").scrollIntoViewIfNeeded();
      checks.push(`${state} blocks close`);
    }
    await capture(page, `es-419-light-390x844-${state}`, "es-419", "light");
    await context.close();
  }
} finally {
  await browser.close();
}
writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, baseURL, fixtureURL,
  source: "actual Next /biz with isolated synthetic loopback fixture API; guide is development/mock-only",
  checks, captures, pageErrors: errors }, null, 2));
assert.deepEqual(errors, [], `uncaught browser errors: ${errors.join(" | ")}`);
console.log(JSON.stringify({ head, captures: captures.length, checks: checks.length, output, errors }, null, 2));
