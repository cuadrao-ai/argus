import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { FREEZE_CSS } from "./support/breakpoint-fixture";
import { AUDIT_CELLS, AUDIT_DIR as evidence, auditTag, openFixture, openSettings, type Cell } from "./support/menu-settings-fixture";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";

// Observational chrome captures. Existing breakpoint baselines remain separate.
async function capture(page: Page, cell: Cell, name: string, marker: Locator) {
  await expect(marker).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  mkdirSync(evidence, { recursive: true });
  await page.screenshot({ path: path.join(evidence, `${auditTag(cell)}-${name}.png`), animations: "disabled", scale: "css" });
}

for (const cell of AUDIT_CELLS.filter((cell) => cell.account === "registered")) {
  test(`${auditTag(cell)} account deletion owns the visible modal`, async ({ page }) => {
    const copy = cell.language === "en" ? en : es;
    await openFixture(page, cell);
    await openSettings(page, cell);
    await page.getByRole("button", { name: copy.settings.data.title, exact: true }).click();
    const openRequest = () => page.getByRole("button", { name: new RegExp(`^${copy.settings.profile.delete_account}`) }).click();
    const dialog = page.getByRole("dialog", { name: copy.settings.profile.request_deletion.title, exact: true });
    const confirm = dialog.getByRole("button", { name: copy.settings.profile.request_deletion.confirm, exact: true });
    for (const close of ["cancel", "escape", "back"] as const) {
      await openRequest();
      await expect(dialog).toBeVisible();
      // Visibility alone passes for a dialog behind another sheet. Hit-test the
      // actual action before any mutation and require one modal presentation.
      await expect.poll(() => confirm.evaluate((node) => {
        const r = node.getBoundingClientRect();
        return node.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
      })).toBe(true);
      await expect(page.locator(".argus-sheet")).toHaveCount(0);
      await page.keyboard.press("Tab");
      await expect.poll(() => dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
      if (close === "cancel") await dialog.getByRole("button", { name: copy.common.cancel, exact: true }).click();
      else if (close === "escape") await page.keyboard.press("Escape");
      else await page.goBack();
      await expect(dialog).toHaveCount(0);
      await expect(page.getByRole("button", { name: copy.settings.data.archived_chats, exact: true })).toBeVisible();
      await expect(page).toHaveURL(/\/chat\?conversation=conversation-alpha/);
    }
  });
}

for (const cell of AUDIT_CELLS.filter((cell) => cell.account === "registered" && cell.width < 720)) {
  test(`${auditTag(cell)} sheet controls meet the 44px contract`, async ({ page }) => {
    const copy = cell.language === "en" ? en : es;
    for (const surface of ["deleted", "language", "rename", "feedback"] as const) {
      await openFixture(page, cell);
      if (surface === "rename") {
        await page.getByRole("button", { name: copy.chat.chat_options, exact: true }).click();
        await page.getByRole("menuitem", { name: copy.chat.rename_chat, exact: true }).click();
      } else {
        await openSettings(page, cell);
        if (surface === "deleted") {
          await page.getByRole("button", { name: copy.settings.data.title, exact: true }).click();
          await page.getByRole("button", { name: copy.settings.data.recently_deleted, exact: true }).click();
          await expect(page.getByRole("button", { name: copy.common.restore, exact: true }).first()).toBeVisible();
        } else if (surface === "language") {
          await page.getByRole("button", { name: copy.settings.preferences.title, exact: true }).click();
          await page.getByRole("button", { name: copy.settings.app.language, exact: true }).click();
        } else {
          await page.getByRole("button", { name: copy.feedback.eyebrow, exact: true }).click();
          await page.getByRole("button", { name: copy.feedback.type.general, exact: true }).click();
        }
      }
      const sheet = page.locator(".argus-sheet");
      await expect(sheet).toHaveCount(1);
      const targets = sheet.locator('button, input:not([type="checkbox"]):not([type="file"]):not([type="hidden"])');
      for (const target of await targets.all()) {
        if (!(await target.isVisible())) continue;
        await target.scrollIntoViewIfNeeded();
        const size = await target.boundingBox();
        expect(size?.width, `${surface} target width`).toBeGreaterThanOrEqual(44);
        expect(size?.height, `${surface} target height`).toBeGreaterThanOrEqual(44);
      }
      const checkbox = sheet.getByRole("checkbox");
      if (await checkbox.count()) {
        const label = sheet.locator('label:has(input[type="checkbox"])');
        await label.scrollIntoViewIfNeeded();
        expect((await label.boundingBox())?.height).toBeGreaterThanOrEqual(44);
        const previous = await checkbox.isChecked();
        await label.click({ position: { x: 24, y: 22 } });
        await expect(checkbox).toBeChecked({ checked: !previous });
      }
    }
  });
}
async function openSearch(page: Page, width: number) {
  if (width < 720) await page.getByTestId("chat-shell-menu-trigger").click();
  await page.getByRole("button", { name: /^(search|buscar)$/i }).first().click();
}

for (const cell of AUDIT_CELLS) {
  test(`${auditTag(cell)} Search and dossier`, async ({ page }) => {
    await openFixture(page, cell);
    await openSearch(page, cell.width);
    const row = page.locator("[data-palette-row-index]").first();
    const menu = row.getByTestId("command-palette-row-menu");
    if (cell.width < 1024) {
      await menu.click();
      await capture(page, cell, "search-row-menu", page.getByRole("menu").last());
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
    } else {
      await expect(menu).toBeHidden();
      await row.hover();
    }
    await capture(page, cell, "search", row);
    if (cell.width < 1024) await row.click();
    const action = page.getByTestId("dossier-sheet-open-conversation");
    await expect(page.locator(".argus-sheet")).toHaveCount(cell.width < 1024 ? 1 : 0);
    await capture(page, cell, "dossier", cell.width < 1024 ? action
      : page.getByRole("button", { name: /retest with current data|volver a probar con datos actuales/i }).first());
  });

  // Guests retain only their current conversation, already covered above.
  if (cell.account === "registered") test(`${auditTag(cell)} plain conversation preview`, async ({ page }) => {
    await openFixture(page, cell);
    await openSearch(page, cell.width);
    const row = page.locator("[data-palette-row-index]").nth(1);
    if (cell.width < 1024) await row.click();
    else await row.hover();
    await expect(page.locator(".argus-sheet")).toHaveCount(cell.width < 1024 ? 1 : 0);
    await capture(page, cell, "conversation-preview", page.getByRole("region", { name: /^(conversation|conversación|preview|vista previa)$/i }).last());
  });

  test(`${auditTag(cell)} Sources`, async ({ page }) => {
    await openFixture(page, cell);
    await page.route("**/api/v1/conversations/*/messages*", (route) => route.request().method() === "GET" ? route.fulfill({
      json: { items: [{
        id: "source-message", role: "assistant", created_at: "2026-09-14T12:00:00Z",
        content: cell.language === "en" ? "Sources for this example." : "Fuentes de este ejemplo.",
        metadata: { discovery: {
          schema_version: "argus_asset_discovery/v1", kind: "asset_discovery",
          relationship: "peer", query_summary: "Apple peers", retrieved_at: "2026-09-14T12:00:00Z",
          unverified_names: [], can_request_search: false,
          candidates: [{ symbol: "MSFT", name: "Microsoft", asset_class: "equity",
            reason_text: cell.language === "en" ? "Technology peer" : "Empresa tecnológica similar", source_indices: [0] }],
          sources: [{ url: "https://example.com/earnings", domain: "example.com",
            title: cell.language === "en" ? "Quarterly earnings summary" : "Resumen de resultados trimestrales", source_date: "2026-09-11" }],
        } },
      }], next_cursor: null },
    }) : route.fallback());
    await page.reload({ waitUntil: "networkidle" });
    await page.addStyleTag({ content: FREEZE_CSS });
    await page.getByRole("button", { name: /1 source|1 fuente/i }).click();
    await expect(page.locator(".argus-sheet")).toHaveCount(cell.width < 1024 ? 1 : 0);
    await capture(page, cell, "sources", page.getByRole("dialog").getByRole("link", { name: /quarterly earnings|resultados trimestrales/i }));
  });
}
