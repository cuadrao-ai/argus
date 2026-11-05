import { expect, test } from "@playwright/test";

import { cuadraoLegalLinks } from "../lib/cuadrao-legal-links";

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

  test("business sign-up still renders", async ({ page }, testInfo) => {
    await page.goto("/?auth=signup");
    await expect(page).toHaveURL(/\/\?auth=signup$/);
    await expect(
      page.getByRole("button", { name: "Sign up", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("signup.png"),
      fullPage: true,
    });
  });

  test("auth callback and account security stay put", async ({ page }) => {
    for (const path of ["/auth/recovery", "/account/security"]) {
      const response = await page.goto(path, { waitUntil: "commit" });
      expect(response?.request().redirectedFrom()).toBeNull();
      expect(new URL(response!.url()).pathname).toBe(path);
    }
  });

  test("privacy and terms stay reachable and leave for the published pages", async ({
    page,
  }) => {
    const { terms, privacy } = cuadraoLegalLinks();
    const published = [privacy, terms].map((url) => new URL(url));
    await page.route(
      (url) => published.some((target) => target.origin === url.origin),
      (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>published</title>" }),
    );

    for (const [path, target] of [
      ["/privacy", privacy],
      ["/terms", terms],
    ] as const) {
      await page.goto(path);
      await page.waitForURL(target);
      expect(page.url(), path).toBe(new URL(target).href);
    }
  });
});
