import { expect, test } from "@playwright/test";

import {
  HOSTED_MODE,
  currentRecoveryPassword,
  expectLoginRejected,
  identities,
  loginViaUi,
  mailpitClear,
  mailpitMessages,
  mailpitWaitForRecoveryLink,
  protectedMeStatus,
  requestRecoveryViaApi,
  requestRecoveryViaUi,
  runIp,
  respectSendWindow,
  saveQaState,
  screenshot,
} from "./helpers";

// Journeys 1-9 of the issue-248 acceptance matrix against the real app,
// real Supabase Auth, and real Mailpit-captured recovery email.
test.use({ extraHTTPHeaders: { "x-forwarded-for": runIp(9) } });

test.describe("issue-248 recovery journeys (local real auth)", () => {
  test.skip(HOSTED_MODE, "hosted recovery delivery is gated on sandbox SMTP");

  test("unknown and known addresses receive identical outward responses", async ({
    context,
  }) => {
    await mailpitClear(context.request);

    const unknown = await requestRecoveryViaApi(
      context,
      "no-such-user-248@qa.argus.local",
      runIp(1),
    );
    expect(unknown.status()).toBe(202);
    const unknownBody = (await unknown.json()) as Record<string, unknown>;

    const known = await requestRecoveryViaApi(
      context,
      identities().recoveryEmail,
      runIp(1),
    );
    expect(known.status()).toBe(202);
    expect((await known.json()) as Record<string, unknown>).toEqual(unknownBody);

    await mailpitWaitForRecoveryLink(context.request, identities().recoveryEmail);
    const inbox = await mailpitMessages(context.request);
    for (const message of inbox.messages) {
      for (const to of message.To) {
        expect(to.Address.toLowerCase()).toBe(identities().recoveryEmail.toLowerCase());
      }
    }
  });

  test("full recovery lifecycle: one exchange, reset, old fails, reuse fails", async ({
    page,
    context,
  }) => {
    const { recoveryEmail } = identities();
    const oldPassword = currentRecoveryPassword();
    await mailpitClear(context.request);

    const consoleLogs: string[] = [];
    page.on("console", (message) => consoleLogs.push(message.text()));
    const documentUrls: string[] = [];
    page.on("request", (request) => {
      if (request.isNavigationRequest()) documentUrls.push(request.url());
    });

    await respectSendWindow();
    await requestRecoveryViaUi(page, recoveryEmail);
    await screenshot(page, "02-forgot-password-generic-sent");
    const { link } = await mailpitWaitForRecoveryLink(context.request, recoveryEmail);

    await page.goto(link);
    await page.waitForURL("**/auth/recovery**");
    await expect(page.getByLabel("New password", { exact: true })).toBeVisible({
      timeout: 20_000,
    });
    const codeUrl = documentUrls.find((url) => url.includes("/auth/recovery?code="));
    expect(codeUrl).toBeTruthy();
    const code = new URL(codeUrl as string).searchParams.get("code") as string;
    await expect(page).toHaveURL(/\/auth\/recovery$/);
    expect(await page.locator('input[type="password"]').count()).toBe(2);
    await screenshot(page, "03-recovery-ready-code-stripped");

    const newPassword = `Qa!R${Date.now().toString(36)}x${Math.random().toString(36).slice(2, 8)}`;
    await page.getByLabel("New password", { exact: true }).fill(newPassword);
    await page.locator('button[type="submit"]').click();
    await expect(page.locator("main").getByRole("status")).toContainText(
      "Sign in again on every browser",
      { timeout: 25_000 },
    );
    saveQaState({ currentPassword: newPassword, usedRecoveryLink: link });
    await screenshot(page, "04-recovery-complete-global-signout");

    expect(page.url()).not.toContain(code);
    for (const line of consoleLogs) expect(line).not.toContain(code);
    const storageDump = await page.evaluate(() =>
      JSON.stringify({ ...window.localStorage, ...window.sessionStorage }),
    );
    expect(storageDump).not.toContain(code);

    await expectLoginRejected(page, recoveryEmail, oldPassword);
    await screenshot(page, "05-old-password-rejected");
    await loginViaUi(page, recoveryEmail, newPassword);
    await screenshot(page, "06-new-password-login");

    const reusePage = await context.newPage();
    await reusePage.goto(link);
    await reusePage.waitForURL("**/auth/recovery**");
    await expect(reusePage.locator("main").getByRole("alert")).toContainText(
      "missing, expired, or already used",
      { timeout: 20_000 },
    );
    await screenshot(reusePage, "07-reused-link-invalid");
    await reusePage.close();
  });

  test("malformed links fail safely; recovery never asks for the old password", async ({
    page,
  }) => {
    await page.goto("/auth/recovery?code=not-a-real-code");
    await expect(page.locator("main").getByRole("alert")).toBeVisible({ timeout: 20_000 });
    expect(await page.locator('input[type="password"]').count()).toBe(0);
    await page.goto("/auth/recovery");
    await expect(page.locator("main").getByRole("alert")).toBeVisible();
    await screenshot(page, "08-malformed-and-missing-code");
  });

  test("expired links fail safely", async ({ page, context }) => {
    test.setTimeout(210_000);
    const { recoveryEmail } = identities();
    await mailpitClear(context.request);
    await respectSendWindow();
    const response = await requestRecoveryViaApi(context, recoveryEmail, runIp(2));
    expect(response.status()).toBe(202);
    const { link } = await mailpitWaitForRecoveryLink(context.request, recoveryEmail);
    // supabase/config.toml pins otp_expiry to 60s for this stack.
    await page.waitForTimeout(70_000);
    await page.goto(link);
    await page.waitForURL("**/auth/recovery**");
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "missing, expired, or already used",
    );
    await screenshot(page, "09-expired-link-invalid");
  });

  test("normal password change rejects a wrong current password", async ({
    page,
    browser,
  }) => {
    // Wrong-current-password enforcement is the provider policy
    // security_update_password_require_current_password, which CLI v2.109.0
    // cannot enable on the local stack; the hosted live matrix proves this
    // journey. Remove the skip when the local CLI can express the policy.
    test.skip(true, "requires the hosted current-password policy");
    const { recoveryEmail } = identities();
    const password = currentRecoveryPassword();
    await loginViaUi(page, recoveryEmail, password);
    await page.goto("/account/security");
    await expect(page.getByRole("heading", { name: "Account security" })).toBeVisible({
      timeout: 20_000,
    });
    await screenshot(page, "10-account-security-direct-nav");

    const attempted = `Qa!W${Date.now().toString(36)}x${Math.random().toString(36).slice(2, 8)}`;
    await page.getByLabel("Current password", { exact: true }).fill("Wrong-current-1!");
    await page.getByLabel("New password", { exact: true }).fill(attempted);
    await page.getByRole("button", { name: "Change password" }).click();

    const alert = page.locator("main").getByRole("alert");
    const status = page.locator("main").getByRole("status");
    await expect(alert.or(status)).toBeVisible({ timeout: 25_000 });
    if (await status.isVisible().catch(() => false)) {
      // Keep the shared identity state coherent before failing loudly.
      saveQaState({ currentPassword: attempted });
      throw new Error(
        "DEFECT(journey 9/11): a wrong current password was accepted and the password mutated",
      );
    }
    await expect(alert).toContainText("current password");
    await screenshot(page, "11-wrong-current-password-rejected");

    const probeContext = await browser.newContext();
    const probePage = await probeContext.newPage();
    await loginViaUi(probePage, recoveryEmail, password);
    await expect.poll(() => protectedMeStatus(probeContext), { timeout: 15_000 }).toBe(200);
    await probeContext.close();
  });

  test("normal password change with the correct current password succeeds and revokes sessions", async ({
    page,
    browser,
  }) => {
    const { recoveryEmail } = identities();
    const password = currentRecoveryPassword();

    const contextB = await browser.newContext();
    const pageB = await contextB.newPage();
    await loginViaUi(pageB, recoveryEmail, password);
    await expect.poll(() => protectedMeStatus(contextB), { timeout: 15_000 }).toBe(200);

    await loginViaUi(page, recoveryEmail, password);
    await page.goto("/account/security");
    const newPassword = `Qa!C${Date.now().toString(36)}x${Math.random().toString(36).slice(2, 8)}`;
    await page.getByLabel("Current password", { exact: true }).fill(password);
    await page.getByLabel("New password", { exact: true }).fill(newPassword);
    await page.getByRole("button", { name: "Change password" }).click();

    const status = page.locator("main").getByRole("status");
    const alert = page.locator("main").getByRole("alert");
    await expect(status.or(alert)).toBeVisible({ timeout: 25_000 });
    if (await alert.isVisible().catch(() => false)) {
      throw new Error("DEFECT(journey 9): the correct current password was rejected");
    }
    saveQaState({ currentPassword: newPassword });
    await expect(status).toContainText("Sign in again");
    await screenshot(page, "12-password-change-success");

    await expect
      .poll(() => protectedMeStatus(contextB), { timeout: 20_000 })
      .toBe(401);
    await expectLoginRejected(page, recoveryEmail, password);
    await loginViaUi(page, recoveryEmail, newPassword);
    await contextB.close();
  });
});
