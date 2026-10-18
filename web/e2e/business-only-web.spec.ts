import { expect, test } from "@playwright/test";

const enabled = process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB !== "false";

test.describe("business-only web", () => {
  test.skip(!enabled, "switch is off for this run");

  test("root and legacy chat land on business sign-in", async ({ page }, testInfo) => {
    for (const path of ["/", "/chat", "/chat/history"]) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/\?auth=login$/);
      await expect(
        page.getByRole("button", { name: "Sign in", exact: true }),
      ).toBeVisible();
    }
    await page.screenshot({
      path: testInfo.outputPath("root-sign-in.png"),
      fullPage: true,
    });
  });

  test("business sign-up still renders", async ({ page }) => {
    await page.goto("/?auth=signup");
    await expect(page).toHaveURL(/\/\?auth=signup$/);
    await expect(
      page.getByRole("button", { name: "Sign up", exact: true }),
    ).toBeVisible();
    mkdirSync(evidenceDir, { recursive: true });
    await page.screenshot({
      path: join(evidenceDir, "signup.png"),
      fullPage: true,
    });
  });

  test("auth callback, account security, privacy, and terms stay put", async ({
    page,
  }, testInfo) => {
    for (const path of [
      "/auth/recovery",
      "/account/security",
      "/privacy",
      "/terms",
    ]) {
      const response = await page.goto(path, { waitUntil: "commit" });
      expect(response?.request().redirectedFrom()).toBeNull();
      expect(new URL(response!.url()).pathname).toBe(path);
    }

    await page.goto("/privacy");
    await expect(
      page.getByRole("heading", { name: "Privacy Policy" }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("privacy.png"),
      fullPage: true,
    });
    await page.goto("/terms");
    await expect(
      page.getByRole("heading", { name: "Terms of Use" }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("terms.png"),
      fullPage: true,
    });
  });
});
