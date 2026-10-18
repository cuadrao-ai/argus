import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

const evidenceDir = join(
  process.cwd(),
  "../docs/reports/evidence/business-only-web",
);

const enabled = process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB !== "false";

test.describe("business-only web", () => {
  test.skip(!enabled, "switch is off for this run");

  test("root and legacy chat land on business sign-in", async ({ page }) => {
    for (const path of ["/", "/chat", "/chat/history"]) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/\?auth=login$/);
      await expect(
        page.getByRole("button", { name: "Sign in", exact: true }),
      ).toBeVisible();
    }
    mkdirSync(evidenceDir, { recursive: true });
    await page.screenshot({
      path: join(evidenceDir, "root-sign-in.png"),
      fullPage: true,
    });
  });

  test("auth callback, account security, privacy, and terms stay put", async ({
    page,
  }) => {
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

    mkdirSync(evidenceDir, { recursive: true });
    await page.goto("/privacy");
    await expect(
      page.getByRole("heading", { name: "Privacy Policy" }),
    ).toBeVisible();
    await page.screenshot({
      path: join(evidenceDir, "privacy.png"),
      fullPage: true,
    });
    await page.goto("/terms");
    await expect(
      page.getByRole("heading", { name: "Terms of Use" }),
    ).toBeVisible();
    await page.screenshot({
      path: join(evidenceDir, "terms.png"),
      fullPage: true,
    });
  });
});
