import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "./support/month-close-wire";
import type { AvatarTheme } from "../lib/avatar-theme";

async function installAccount(page: Page) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const profile = {
    id: "avatar-user", email: "avatar@example.test", username: "avatar-user", display_name: "Ana Luna", preferred_name: "Ana Luna",
    language: "es-419", locale: "es-419", avatar_theme: undefined as AvatarTheme | undefined,
    onboarding: { completed: true, stage: "completed", language_confirmed: true },
  };
  const patches: AvatarTheme[] = [];
  await page.route("**/api/v1/me", async (route) => {
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON();
      profile.avatar_theme = patch.avatar_theme;
      patches.push(patch.avatar_theme);
    }
    return route.fulfill({ json: { user: profile, account_kind: "registered" } });
  });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    let json: unknown;
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    if (path === "space") json = await source.ensureSpace("es-419");
    else if (path === "spaces") json = { spaces: await source.spaces() };
    else if (path === "workspace") json = await source.workspace();
    else if (path === "overview") json = await source.overview("2026-10-01", "2026-10-31");
    else if (path === "receipts") json = await source.receiptPage!("inbox");
    else if (path === "email") json = await source.emailIntake();
    else if (path === "receipt-reading") json = { enabled: false, available: true, can_change: true };
    else if (path === "month-close") json = monthCloseWire(url.searchParams.get("month") ?? "2026-10");
    else if (path === "open-items") json = OPEN_ITEMS_WIRE;
    else if (["captures", "expenses", "email/deliveries"].includes(path)) json = { items: [] };
    else return route.fulfill({ status: 404, json: { code: "fixture_only" } });
    return route.fulfill({ json });
  });
  return { patches };
}

for (const width of [1440, 390]) {
  test(`saved account color replaces the name tint and survives reload at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const { patches } = await installAccount(page);
    await page.goto("/biz");
    const account = page.getByTestId("header-profile-trigger").filter({ visible: true });
    const mark = account.locator("[aria-hidden=true]").first();
    await expect(mark).toHaveText("AL");
    const fallback = await mark.evaluate((node) => getComputedStyle(node).backgroundColor);
    expect(fallback).not.toBe("rgb(218, 241, 222)");
    await page.reload();
    await expect(mark).toHaveCSS("background-color", fallback);
    await account.click();
    await page.getByRole("button", { name: "Perfil", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Perfil", exact: true });
    await dialog.locator("[data-avatar-theme-trigger]").click();
    const picker = dialog.getByRole("radiogroup");
    await expect(picker).toBeVisible();
    await picker.getByRole("radio").last().click();
    await expect.poll(() => patches).toEqual(["plum"]);
    await expect(dialog.locator("[data-avatar-theme-trigger]").locator("span").first()).toHaveCSS("background-color", "rgb(218, 241, 222)");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    if (await account.getAttribute("aria-expanded") === "true") await page.keyboard.press("Escape");
    await testInfo.attach(`saved-account-${width}`, { body: await page.screenshot(), contentType: "image/png" });
    const evidence = process.env.ACCOUNT_AVATAR_EVIDENCE_DIR;
    if (evidence) await page.screenshot({ path: `${evidence}/account-${width}.png` });
    await expect(mark).toHaveCSS("background-color", "rgb(218, 241, 222)");
    await page.reload();
    await expect(mark).toHaveCSS("background-color", "rgb(218, 241, 222)");
    await expect(mark).toHaveText("AL");
  });
}
