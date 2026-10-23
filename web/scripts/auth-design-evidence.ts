import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium, webkit, expect, type Locator } from "@playwright/test";
import { installBreakpointFixture } from "../e2e/support/breakpoint-fixture";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

const baseURL = process.env.EVIDENCE_BASE_URL ?? "http://127.0.0.1:3199";
assert.ok(["127.0.0.1", "localhost"].includes(new URL(baseURL).hostname));
const head = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const output = resolve(process.env.EVIDENCE_OUTPUT ?? "../temp/auth-design-evidence");
mkdirSync(output, { recursive: true });
const engine = process.env.EVIDENCE_BROWSER === "webkit" ? webkit : chromium;
const browser = await engine.launch({ headless: true });
const captures: object[] = [];
const position = (locator: Locator) => locator.evaluate(element => element.getBoundingClientRect().y + scrollY);
try {
  const widths = process.env.EVIDENCE_WIDTHS?.split(",").map(Number) ?? [320, 360, 390, 768, 1024, 1280, 1440];
  for (const width of widths) for (const language of ["es-419", "en"] as const) for (const theme of ["light", "dark"] as const) for (const mode of ["signup", "login"] as const) {
    const height = width < 768 ? 844 : 900;
    const page = await browser.newPage({ viewport: { width, height }, colorScheme: theme, reducedMotion: "reduce" });
    await page.clock.install();
    const errors: string[] = [];
    const blocked: string[] = [];
    let signups = 0, verifies = 0, resends = 0;
    let acceptResend: (() => Promise<void>) | undefined;
    page.on("pageerror", error => errors.push(error.message));
    await installBreakpointFixture(page, { language, theme, emptyChat: true });
    await page.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url());
      if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
        blocked.push(`${request.method()} ${url.pathname}`);
        return route.abort();
      }
      if (url.pathname.endsWith("/auth/signup")) {
        signups++;
        return route.fulfill({ json: { user: { id: "pending", email: "synthetic@example.test" }, session: null } });
      }
      if (url.pathname === "/auth/v1/verify") {
        verifies++;
        assert.equal(request.postDataJSON().token, "01234567");
        return route.fulfill({ status: verifies === 1 ? 503 : 403, json: { code: verifies === 1 ? "unexpected_failure" : "otp_expired", msg: "synthetic rejection" } });
      }
      if (url.pathname === "/auth/v1/resend") {
        resends++;
        assert.deepEqual(request.postDataJSON(), { email: "synthetic@example.test", type: "signup", gotrue_meta_security: { captcha_token: "argus-local-browser-qa" } });
        if (resends === 1) return route.fulfill({ status: 429, headers: { "Retry-After": "65" }, json: { code: "over_email_send_rate_limit" } });
        if (resends === 2) return route.fulfill({ status: 503, json: { code: "unexpected_failure" } });
        if (resends === 3) return route.fulfill({ status: 400, json: { code: "captcha_failed" } });
        return new Promise<void>(done => { acceptResend = async () => { await route.fulfill({ json: {} }); done(); }; });
      }
      if (url.pathname === "/auth/v1/user") return route.fulfill({ status: 401, json: { msg: "no synthetic session" } });
      return route.fallback();
    });
    const copy = language === "en" ? en : es;
    const prefix = `${language}-${theme}-${width}-${mode}`;
    const capture = async (state: string) => {
      const file = `${prefix}-${state}.png`;
      await page.evaluate(() => {
        const mark = document.createElement("div");
        mark.dataset.authEvidenceWatermark = "true";
        mark.textContent = "MOCK AUTH CAPTURE";
        mark.setAttribute("aria-hidden", "true");
        Object.assign(mark.style, { position: "fixed", top: "8px", left: "8px", zIndex: "9999", padding: "4px 8px",
          background: "#ffda80", color: "#172b26", borderRadius: "4px", font: "bold 12px sans-serif", pointerEvents: "none" });
        document.body.append(mark);
      });
      let image: Buffer;
      try {
        image = await page.screenshot({ path: resolve(output, file), fullPage: true, animations: "disabled", scale: "css" });
      } finally {
        await page.locator('[data-auth-evidence-watermark="true"]').evaluate(node => node.remove());
      }
      const baseline = process.env.EVIDENCE_BASELINE ? resolve(process.env.EVIDENCE_BASELINE, file) : "";
      captures.push({ file, head, sha256: createHash("sha256").update(image).digest("hex"), width, height, language, theme, mode, state, baselineIdentical: baseline && existsSync(baseline) ? image.equals(readFileSync(baseline)) : null });
    };
    const noOverflow = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${prefix} overflow`);
    await page.goto(`${baseURL}/?auth=${mode}`, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    const email = page.locator('input[type="email"]'), password = page.locator('input[autocomplete$="password"]'), submit = page.locator('form button[type="submit"]');
    await expect(page.getByRole("heading", { name: copy.auth[mode].title, exact: true })).toBeVisible();
    await capture("identity");
    await noOverflow();
    await email.fill("wrong");
    await submit.click();
    assert.equal(signups, 0);
    await expect(email).toBeFocused();
    await email.fill("synthetic@example.test");
    const buttonIdentity = await submit.elementHandle();
    await submit.click();
    assert.equal(signups, 0);
    await expect(password).toBeFocused();
    assert.equal(await buttonIdentity?.evaluate(element => element.isConnected), true);
    await password.fill("synthetic long password 47");
    await capture("password");
    await noOverflow();
    const eye = page.locator("form button[aria-controls]");
    await eye.press("Space");
    assert.equal(await password.getAttribute("type"), "text");
    await eye.press("Enter");
    assert.equal(await password.getAttribute("type"), "password");
    if (mode === "signup") {
      await submit.click();
      await expect(page.getByTestId("auth-check-email")).toBeVisible();
      assert.equal(signups, 1);
      await capture("confirmation");
      const code = page.getByTestId("auth-confirmation-code"), confirm = page.locator('form button[type="submit"]');
      assert.equal(await page.locator("[data-otp-slot]").count(), 8);
      await page.evaluate(() => document.fonts.ready);
      const before = await position(confirm);
      const stable = async () => { await page.evaluate(() => document.fonts.ready); assert.ok(Math.abs(before - await position(confirm)) < 1, `${prefix} CTA moved ${before} to ${await position(confirm)} for ${await page.locator("#auth-confirmation-code-note").textContent()}`); await noOverflow(); };
      await code.fill("012");
      await confirm.click();
      assert.equal(verifies, 0);
      await stable();
      await code.fill("012345678");
      await confirm.click();
      assert.equal(verifies, 0);
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_code_malformed.replace("{{count}}", "8"));
      await stable();
      await code.evaluate(element => { const transfer = new DataTransfer(); transfer.setData("text", "0123 4567"); element.dispatchEvent(new ClipboardEvent("paste", { clipboardData: transfer, bubbles: true })); });
      await expect(code).toHaveValue("01234567");
      await code.press("End");
      await code.press("Backspace");
      await code.press("7");
      await confirm.click();
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_temporary_error);
      await expect(code).toHaveValue("01234567");
      await stable();
      await capture("transient");
      await confirm.click();
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_code_rejected);
      await expect(code).toHaveValue("");
      await expect(code).toBeFocused();
      await stable();
      await capture("rejected");
      await page.clock.fastForward(31_000);
      const resend = page.getByRole("button", { name: copy.auth.signup.confirmation_resend, exact: true });
      await resend.click();
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_rate_limited);
      await expect(page.locator("button").filter({ hasText: copy.auth.signup.confirmation_resend_wait.split("{{seconds}}")[0] })).toBeDisabled();
      await stable();
      await capture("rate-limited");
      await page.clock.fastForward(65_000);
      await resend.click();
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_resend_failed);
      await stable();
      await resend.click();
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_resend_failed);
      await stable();
      await capture("captcha-refused");
      await resend.click();
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_resend_pending);
      await expect(confirm).toBeDisabled();
      assert.ok(acceptResend);
      await acceptResend();
      await expect(page.locator("#auth-confirmation-code-note")).toHaveText(copy.auth.signup.confirmation_resend_sent);
      await stable();
      await capture("resend-accepted");
      assert.equal(verifies, 2);
      assert.equal(resends, 4);
      await page.reload({ waitUntil: "networkidle" });
      await expect(email).toHaveValue("");
      assert.equal(resends, 4);
    } else {
      await page.getByRole("button", { name: copy.auth.form.edit_email, exact: true }).click();
      await expect(email).toHaveValue("synthetic@example.test");
      await submit.click();
      await expect(password).toHaveValue("");
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(blocked, []);
    await page.close();
  }
} finally {
  await browser.close();
  writeFileSync(resolve(output, "manifest.json"), JSON.stringify({ head, browser: engine.name(), synthetic: true, captures }, null, 2));
}
console.log(JSON.stringify({ head, browser: engine.name(), captures: captures.length, output }));
