import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";
import { installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const CONTACT_PAGE = { "es-419": "https://cuadrao.ai/contacto", en: "https://cuadrao.ai/en/contact" } as const;
const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3199";
assert.ok(["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname));
const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/auth-design-evidence/invite-only");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const captures: object[] = [];
try {
  for (const width of [1440, 390] as const) for (const language of ["es-419", "en"] as const) {
    const height = width < 768 ? 844 : 900;
    const copy = language === "en" ? en : es;
    const page = await browser.newPage({ viewport: { width, height }, colorScheme: "light", reducedMotion: "reduce" });
    const errors: string[] = [];
    const blocked: string[] = [];
    let signups = 0;
    page.on("pageerror", error => errors.push(error.message));
    await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
    await page.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url());
      if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
        blocked.push(`${request.method()} ${url.pathname}`);
        return route.abort();
      }
      if (url.pathname.endsWith("/auth/signup")) {
        signups++;
        return route.fulfill({ status: 400, json: { code: "auth_signup_failed", title: "Signup Failed", detail: "Signup failed. Please try again." } });
      }
      return route.fallback();
    });
    const capture = async (state: string) => {
      const file = `${language}-${width}-${state}.png`;
      const image = await page.screenshot({ path: resolve(output, file), fullPage: true, animations: "disabled", scale: "css" });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${file} overflow`);
      captures.push({ file, head, sha256: createHash("sha256").update(image).digest("hex"), width, height, language, state });
    };

    await page.goto(`${baseURL}/?auth=login`, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { name: copy.auth.login.title, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: copy.auth.signup.submit, exact: true })).toBeVisible();
    await expect(page.getByTestId("invite-only-refusal")).toHaveCount(0);
    await capture("login");

    await page.goto(`${baseURL}/?auth=signup`, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    await expect(page.getByRole("heading", { name: copy.auth.signup.title, exact: true })).toBeVisible();
    const email = page.locator('input[type="email"]'), password = page.locator('input[autocomplete$="password"]'), submit = page.locator('form button[type="submit"]');
    await email.fill("nobody@example.test");
    await submit.click();
    await expect(password).toBeFocused();
    await password.fill("synthetic long password 47");
    await submit.click();
    const refusal = page.getByTestId("invite-only-refusal");
    await expect(refusal).toHaveText(`${copy.auth.invite_only.body} ${copy.auth.invite_only.request_access}`);
    assert.equal(await refusal.locator("a").getAttribute("href"), CONTACT_PAGE[language]);
    assert.equal(await refusal.locator("a").getAttribute("target"), null);
    assert.equal(signups, 1);
    await capture("refused");

    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    await page.close();
  }
} finally {
  await browser.close();
  writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, browser: "chromium", synthetic: true, captures }, null, 2));
}
console.log(JSON.stringify({ head, captures: captures.length, output }));
