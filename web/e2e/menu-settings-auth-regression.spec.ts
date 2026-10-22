import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { AUDIT_CELLS, AUDIT_DIR as evidence, auditTag, openFixture } from "./support/menu-settings-fixture";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

for (const cell of AUDIT_CELLS.filter((cell) => cell.account === "guest")) {
  test(`${auditTag(cell)} auth theme controls and footer language stay accessible`, async ({ page }) => {
    const copy = cell.language === "en" ? en : es;
    await openFixture(page, cell, "/?auth=login");
    const appearance = page.getByRole("group", { name: copy.settings.app.appearance, exact: true });
    for (const label of Object.values(copy.settings.app.appearance_options)) {
      await expect(appearance.getByRole("button", { name: label, exact: true })).toBeVisible();
    }
    await expect(page.getByRole("menu")).toHaveCount(0);
    await expect(page.locator(".argus-sheet")).toHaveCount(0);
    for (const theme of [cell.theme === "light" ? "dark" : "light", cell.theme ?? "dark"] as const) {
      const option = appearance.getByRole("button", { name: copy.settings.app.appearance_options[theme], exact: true });
      await option.click();
      await expect(option).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("html")).toHaveClass(new RegExp(`\\b${theme}\\b`));
    }
    const system = appearance.getByRole("button", { name: copy.settings.app.appearance_options.system, exact: true });
    await system.focus();
    await page.keyboard.press("Space");
    await expect(system).toHaveAttribute("aria-pressed", "true");
    await expect(system).toBeFocused();
    await page.emulateMedia({ colorScheme: "light" });
    await expect(page.locator("html")).toHaveClass(/\blight\b/);
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("html")).toHaveClass(/\bdark\b/);
    await page.evaluate(() => document.fonts.ready);
    mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `${auditTag(cell)}-auth-theme-controls.png`), animations: "disabled", scale: "css" });
    const language = page.getByTestId("auth-language-switch").getByRole("button", { name: cell.language === "en" ? /^Español/ : /^English/ });
    await language.focus();
    await expect(language).toBeFocused();
    await page.keyboard.press("Enter");
    const changedCopy = cell.language === "en" ? es : en;
    await expect(page.getByRole("heading", { name: changedCopy.auth.login.title, exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: changedCopy.settings.app.appearance, exact: true })).toBeVisible();
    await expect(page.getByTestId("auth-language-switch").getByRole("button")).toBeVisible();
    await expect.poll(() => page.evaluate(() => localStorage.getItem("i18nextLng"))).toBe(cell.language === "en" ? "es-419" : "en");
    await expect(page).toHaveURL(/\?auth=login/);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.screenshot({ path: path.join(evidence, `${auditTag(cell)}-auth-footer-language.png`), animations: "disabled", scale: "css" });
  });
}
