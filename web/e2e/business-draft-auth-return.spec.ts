import { expect, test } from "@playwright/test";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

test("sign-in returns to the exact canonical draft after the signed-out link bounce", async ({ page }) => {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const id = dossierFixtureIds.ready;
  await page.goto(`/?auth=login&return_to=${encodeURIComponent(`/biz?draft=${id}&unexpected=drop`)}`);
  await page.locator('input[type="email"]').fill("ejemplo-local@example.com");
  await page.locator('input[type="password"]').fill("synthetic-local-password");
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(`/biz?draft=${id}`);
  expect(new URL(page.url()).searchParams.has("unexpected")).toBe(false);
});

test("signed-out Business draft redirects with its canonical ID", async ({ page }) => {
  test.skip(process.env.NEXT_PUBLIC_MOCK_AUTH !== "false" || process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "Requires the isolated signed-out pilot verification environment");
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const id = dossierFixtureIds.ready;
  await page.goto(`/biz?draft=${id}&unexpected=drop`);
  await expect(page).toHaveURL(/\/\?.*auth=login/);
  expect(new URL(page.url()).searchParams.get("return_to")).toBe(`/biz?draft=${id}`);
  expect(new URL(page.url()).searchParams.has("unexpected")).toBe(false);
  await expect(page.locator('input[type="email"]')).toBeVisible();
});
