import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, webkit, expect, type Locator } from "@playwright/test";
import { installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3199";
assert.ok(["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname), "Evidence requires localhost");
const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/auth-design-evidence");
mkdirSync(output, { recursive: true });
const engine = process.env.EVIDENCE_BROWSER === "webkit" ? webkit : chromium;
const browser = await engine.launch({ headless: true });
const captures: object[] = [];
const position = (locator: Locator) => locator.evaluate((element) => {
  const rect = element.getBoundingClientRect();
  return { x: rect.x, y: rect.y + scrollY, width: rect.width, bottom: rect.bottom + scrollY };
});
try {
  for (const [width, height] of [[320, 568], [390, 844], [768, 1024], [1024, 768], [1279, 800], [1280, 720], [1440, 900], [2553, 1348]]) {
    for (const language of ["es-419", "en"] as const) for (const theme of ["light", "dark"] as const) for (const mode of ["signup", "login"] as const) {
      const page = await browser.newPage({ viewport: { width, height }, colorScheme: theme, reducedMotion: "reduce" });
      const errors: string[] = [];
      const blocked: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      await installBreakpointFixture(page, { language, theme, emptyChat: true });
      await page.route("**/*", (route) => {
        const request = route.request();
        if (!["127.0.0.1", "localhost"].includes(new URL(request.url()).hostname) || request.method() !== "GET") {
          blocked.push(`${request.method()} ${new URL(request.url()).pathname}`);
          return route.abort();
        }
        return route.fallback();
      });
      await page.goto(`${baseURL}/?auth=${mode}`, { waitUntil: "networkidle" });
      await page.evaluate(() => document.fonts.ready);
      const copy = language === "en" ? en : es;
      assert.ok(await page.title(), "Page has a title");
      await expect(page.getByRole("heading", { name: copy.auth[mode].title, exact: true })).toBeVisible();
      assert.equal(await page.locator("nextjs-portal [data-nextjs-dialog]").count(), 0, "No framework error overlay");
      const email = page.locator('input[type="email"]');
      const password = page.locator('input[autocomplete$="password"]');
      const submit = page.locator('form button[type="submit"]');
      const hero = page.getByTestId("auth-hero");
      const heroBefore = await position(hero);
      assert.equal(await email.evaluate((element) => document.activeElement === element), false);
      assert.equal((await position(page.locator("[data-auth-logo] h1 > span"))).width, width >= 768 && width < 1280 ? 200 : 268);
      const layout = await page.locator("main").evaluate((element) => ({ display: getComputedStyle(element).display, gradient: getComputedStyle(element).backgroundImage }));
      assert.equal(layout.display, width >= 1280 ? "grid" : "flex");
      assert.equal(layout.gradient === "none", width < 1280);
      if (mode === "signup") {
        const first = await position(page.locator('input[autocomplete="given-name"]'));
        const last = await position(page.locator('input[autocomplete="family-name"]'));
        assert.equal((Math.abs(first.y - last.y) < 1), width >= 768);
      }
      const file = `${engine.name()}-${language}-${theme}-${width}-${mode}.png`;
      const image = await page.screenshot({ path: resolve(output, file), fullPage: true, animations: "disabled", scale: "css" });
      await email.fill("wrong");
      await password.focus();
      assert.equal(await email.getAttribute("aria-invalid"), "true");
      const engagedSubmit = await position(submit);
      await password.fill("a");
      await email.focus();
      await submit.click();
      assert.equal(await email.evaluate((element) => document.activeElement === element), true);
      assert.equal(await page.getByTestId("form-error-summary").count(), 0);
      await email.fill("synthetic@example.test");
      await password.fill("synthetic long password 47");
      assert.ok(Math.abs(engagedSubmit.y - (await position(submit)).y) < 1, "Validation keeps submit stable");
      if (width >= 768) assert.ok(Math.abs(heroBefore.y - (await position(hero)).y) < 1, "Interaction keeps hero stable");
      if (width >= 1024 && width <= 1280) assert.ok(engagedSubmit.bottom <= height + 2, "Submit fits short desktop");
      const eye = page.locator("form button[aria-controls]");
      await eye.click();
      assert.equal(await password.getAttribute("type"), "text");
      await eye.press("Space");
      assert.equal(await password.getAttribute("type"), "password");
      await eye.press("Enter");
      assert.equal(await password.getAttribute("type"), "text");
      assert.equal(await password.inputValue(), "synthetic long password 47");
      const appearance = page.getByRole("group", { name: copy.settings.app.appearance, exact: true });
      const alternate = theme === "light" ? "dark" : "light";
      await appearance.getByRole("button", { name: copy.settings.app.appearance_options[alternate], exact: true }).click();
      assert.ok(await page.locator("html").evaluate((element, selected) => element.classList.contains(selected), alternate));
      await page.getByTestId("auth-language-switch").getByRole("button").click();
      const changed = language === "en" ? es : en;
      await expect(page.getByRole("heading", { name: changed.auth[mode].title, exact: true })).toBeVisible();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.deepEqual(errors, []);
      assert.deepEqual(blocked, []);
      captures.push({ file, sha256: createHash("sha256").update(image).digest("hex"), width, height, language, theme, mode, layout, checks: "layout, labels, validation, focus, stable submit, eye keyboard, theme, footer language, no overflow or external requests" });
      await page.close();
    }
  }
} finally {
  await browser.close();
}
writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, browser: engine.name(), synthetic: true, captures }, null, 2));
console.log(JSON.stringify({ head, browser: engine.name(), captures: captures.length, output }));
