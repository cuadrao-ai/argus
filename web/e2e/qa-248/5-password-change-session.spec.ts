import { expect, test, type Browser } from "@playwright/test";

import {
  HOSTED_MODE,
  authSessionsCount,
  currentRecoveryPassword,
  identities,
  loginViaUi,
  supabaseSessionId,
} from "./helpers";

// Session-integrity pins for the normal password-change path: the change is
// one native updateUser({password, current_password}) request, so a rejected
// update must leave the browser on its original session, keep the Argus
// cookies, and add no auth.sessions row. The same-password rejection drives
// the failure deterministically without depending on the hosted
// current-password policy.
async function loginFresh(browser: Browser, email: string, password: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await loginViaUi(page, email, password);
  return { context, page };
}

test.describe("issue-248 password-change session integrity (local)", () => {
  test.skip(HOSTED_MODE, "local-only session-state proof");

  test("a failed update preserves the original session and adds no auth.sessions row", async ({
    browser,
  }) => {
    const { recoveryEmail } = identities();
    const password = currentRecoveryPassword();
    const { context, page } = await loginFresh(browser, recoveryEmail, password);

    const originalSessionId = await supabaseSessionId(context);
    expect(originalSessionId).toBeTruthy();
    const rowsBefore = authSessionsCount(recoveryEmail);

    await page.goto("/account/security");
    // Same-password update passes every client check, then the provider
    // rejects it — a failed update after a legitimate attempt.
    await page.getByLabel("Current password", { exact: true }).fill(password);
    await page.getByLabel("New password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.locator("main").getByRole("alert")).toBeVisible({
      timeout: 25_000,
    });

    const afterSessionId = await supabaseSessionId(context);
    expect(afterSessionId).toBe(originalSessionId);
    if (rowsBefore !== null) {
      expect(authSessionsCount(recoveryEmail)).toBe(rowsBefore);
    }

    // The browser stays signed in: the security page still loads normally.
    await page.reload();
    await expect(page.getByRole("heading", { name: "Account security" })).toBeVisible({
      timeout: 20_000,
    });
    await context.close();
  });
});
