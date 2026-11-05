import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

import {
  currentRecoveryPassword,
  identities,
  loginViaUi,
  protectedMeStatus,
  screenshot,
} from "./helpers";

async function loginNewContext(
  browser: Browser,
  email: string,
  password: string,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await loginViaUi(page, email, password);
  return { context, page };
}

// Journeys 10-17 of the issue-248 acceptance matrix: independent sessions,
// scoped revocation, revoked-bearer rejection, honest degraded states.
// The Argus HttpOnly cookie transport is proven separately in
// 6-argus-cookie-path.spec.ts.
test.describe("issue-248 session scope journeys (local real auth)", () => {
  test("revoke-others keeps this browser and rejects the other's revoked bearer token", async ({
    browser,
  }) => {
    const { recoveryEmail } = identities();
    const password = currentRecoveryPassword();
    const a = await loginNewContext(browser, recoveryEmail, password);
    const b = await loginNewContext(browser, recoveryEmail, password);
    await expect.poll(() => protectedMeStatus(a.context), { timeout: 15_000 }).toBe(200);
    await expect.poll(() => protectedMeStatus(b.context), { timeout: 15_000 }).toBe(200);

    await a.page.goto("/account/security");
    await a.page.getByRole("button", { name: "Sign out other sessions" }).click();
    await a.page.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(a.page.locator("main").getByRole("status")).toContainText("Other sessions are signed out", {
      timeout: 20_000,
    });
    await screenshot(a.page, "20-revoke-others-success");

    await expect.poll(() => protectedMeStatus(a.context), { timeout: 15_000 }).toBe(200);
    await expect
      .poll(() => protectedMeStatus(b.context), { timeout: 20_000 })
      .toBe(401);
    await b.page.reload();
    await b.page
      .waitForURL((url) => !url.pathname.startsWith("/chat"), { timeout: 30_000 })
      .catch(() => undefined);
    await screenshot(b.page, "21-revoked-context-after-reload");
    await expect.poll(() => protectedMeStatus(b.context), { timeout: 15_000 }).toBe(401);

    await a.context.close();
    await b.context.close();
  });

  test("revoke-all rejects both contexts and requires a fresh login", async ({ browser }) => {
    const { recoveryEmail } = identities();
    const password = currentRecoveryPassword();
    const a = await loginNewContext(browser, recoveryEmail, password);
    const b = await loginNewContext(browser, recoveryEmail, password);

    await a.page.goto("/account/security");
    await a.page.getByRole("button", { name: "Sign out all sessions" }).click();
    await a.page.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(a.page.locator("main").getByRole("status")).toContainText(
      "The selected sessions are signed out",
      { timeout: 20_000 },
    );
    await expect(a.page.getByRole("link", { name: "Back to sign in" })).toBeVisible();
    await screenshot(a.page, "22-revoke-all-success");

    await expect.poll(() => protectedMeStatus(a.context), { timeout: 20_000 }).toBe(401);
    await expect.poll(() => protectedMeStatus(b.context), { timeout: 20_000 }).toBe(401);

    const fresh = await loginNewContext(browser, recoveryEmail, password);
    await expect.poll(() => protectedMeStatus(fresh.context), { timeout: 15_000 }).toBe(200);
    await screenshot(fresh.page, "23-fresh-login-after-revoke-all");

    await a.context.close();
    await b.context.close();
    await fresh.context.close();
  });

  test("ordinary logout signs out only this browser", async ({ browser }) => {
    const { recoveryEmail } = identities();
    const password = currentRecoveryPassword();
    const a = await loginNewContext(browser, recoveryEmail, password);
    const b = await loginNewContext(browser, recoveryEmail, password);

    // The sidebar may start collapsed and its hover behavior can swallow the
    // first toggle, so expand it and re-open the menu once if needed.
    const openProfileMenu = async () => {
      const expand = a.page.getByRole("button", { name: "Expand", exact: true });
      if (await expand.isVisible().catch(() => false)) {
        await expand.click();
      }
      await a.page.getByRole("button", { name: "Settings" }).click();
    };
    const logoutButton = a.page.getByRole("button", { name: "Log out" });
    await openProfileMenu();
    try {
      await logoutButton.waitFor({ state: "visible", timeout: 5_000 });
    } catch {
      await openProfileMenu();
      await logoutButton.waitFor({ state: "visible", timeout: 10_000 });
    }
    await logoutButton.click();
    await a.page.waitForURL((url) => !url.pathname.startsWith("/chat"), {
      timeout: 30_000,
    });
    await screenshot(a.page, "24-ordinary-logout-landing");

    await expect.poll(() => protectedMeStatus(a.context), { timeout: 20_000 }).toBe(401);
    await expect.poll(() => protectedMeStatus(b.context), { timeout: 15_000 }).toBe(200);
    await screenshot(b.page, "25-other-context-survives-ordinary-logout");

    await a.context.close();
    await b.context.close();
  });

  test("partial cookie-cleanup failure is reported honestly", async ({ browser }) => {
    const { secondEmail, secondPassword } = identities();
    const a = await loginNewContext(browser, secondEmail, secondPassword);

    await a.page.goto("/account/security");
    await a.context.route("**/auth/logout", (route) => route.abort());
    await a.page.getByRole("button", { name: "Sign out this browser" }).click();
    await expect(a.page.locator("main").getByRole("alert")).toContainText("cookie cleanup", {
      timeout: 20_000,
    });
    await screenshot(a.page, "28-partial-cookie-cleanup-warning");
    await a.context.unroute("**/auth/logout");

    // Supabase revocation succeeded; replaying this context's revoked bearer
    // token must be rejected by the auth.sessions check (cookie-path proof
    // lives in 6-argus-cookie-path.spec.ts).
    await expect.poll(() => protectedMeStatus(a.context), { timeout: 20_000 }).toBe(401);
    await a.context.close();
  });
});
