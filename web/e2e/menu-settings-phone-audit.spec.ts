import { expect, test, type Locator, type Page } from "@playwright/test";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import en from "../public/locales/en/common.json";
import es from "../public/locales/es-419/common.json";
import { FREEZE_CSS, type Language } from "./support/breakpoint-fixture";
import { AUDIT_CELLS, AUDIT_DIR, auditTag, openFixture, openSettings, type Cell } from "./support/menu-settings-fixture";

// The labels derive from the shipped locale catalogs, including nested picker
// labels. Nothing in this walk submits a mutation or creates a model turn.
function label(language: Language, key: string): string {
  let value: unknown = language === "en" ? en : es;
  for (const part of key.split(".")) value = (value as Record<string, unknown>)[part];
  if (typeof value !== "string") throw new Error(`Missing locale label: ${key}`);
  return value;
}
function button(page: Page, cell: Cell, key: string) {
  return page.getByRole("button", { name: label(cell.language, key), exact: true }).last();
}
type Surface = { name: string; path: string[]; marker?: string; optional?: boolean; minWidth?: number };
const DATA = "settings.data.title";
const PREFS = "settings.preferences.title";
const FEEDBACK = "feedback.eyebrow";
const REGISTERED: Surface[] = [
  { name: "settings-root", path: [], marker: "settings.profile.title" },
  { name: "profile", path: ["settings.profile.title"] },
  { name: "data", path: [DATA], marker: "settings.data.archived_chats" },
  { name: "preferences", path: [PREFS], marker: "settings.app.appearance" },
  { name: "help", path: ["settings.help.title"], marker: "settings.help.terms" },
  { name: "feedback-menu", path: [FEEDBACK], marker: "feedback.type.bug" },
  { name: "archived", path: [DATA, "settings.data.archived_chats"] },
  { name: "deleted", path: [DATA, "settings.data.recently_deleted"] },
  { name: "usage", path: [DATA, "settings.data.usage"] },
  { name: "shared-links", path: [DATA, "settings.data.shared_links"], optional: true },
  { name: "account-delete", path: [DATA, "settings.profile.delete_account"] },
  { name: "appearance", path: [PREFS, "settings.app.appearance"] },
  { name: "language", path: [PREFS, "settings.app.language"] },
  { name: "country", path: [PREFS, "settings.app.home_country"] },
  { name: "sidebar-preference", path: [PREFS, "settings.app.sidebar"], minWidth: 720 },
  { name: "keyboard-shortcuts", path: ["settings.help.title", "keyboard_shortcuts.menu_item"], minWidth: 720 },
  ...["bug", "feature", "general"].map((kind) => ({
    name: `feedback-${kind}`, path: [FEEDBACK, `feedback.type.${kind}`],
  })),
];
const GUEST: Surface[] = [
  { name: "settings-root", path: [], marker: "guest.shell.language" },
  { name: "language", path: ["guest.shell.language"] },
  { name: "feedback-general", path: ["guest.shell.feedback"] },
];

async function capture(page: Page, cell: Cell, name: string, marker: Locator) {
  await expect(marker).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", cell.language);
  await expect(page.locator("html")).toHaveClass(new RegExp(`(^| )${cell.theme ?? "dark"}( |$)`));
  // A visible dialog may still contain its async loading state.
  if (["archived", "deleted"].includes(name)) {
    await expect(page.getByRole("button", { name: label(cell.language, "common.restore"), exact: true })
      .or(page.getByRole("button", { name: label("en", "common.restore"), exact: true })).first()).toBeVisible();
  } else if (name === "usage") {
    await expect(page.getByRole("progressbar").first()).toBeVisible();
  } else if (["profile", "avatar", "profile-language"].includes(name)) {
    await expect(page.getByText("Alexandra Featherstonehaugh", { exact: true }).last()).toBeVisible();
  }
  await expect(page.locator(".animate-spin").filter({ visible: true })).toHaveCount(0);
  const geometry = await marker.evaluate((element) => {
    const surface = element.closest('[role="dialog"], [role="alertdialog"], [role="menu"], [data-profile-menu-surface]')
      ?? element.closest("form") ?? element.closest("main") ?? element;
    const rect = surface.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    const controls = [...surface.querySelectorAll("button, a, input, textarea, [role=radio]")].flatMap((node) => {
      const r = node.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return [];
      const target = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return [{ name: node.getAttribute("aria-label") ?? node.textContent?.trim(), width: r.width, height: r.height,
        centerHitInside: target !== null && node.contains(target), coveringClass: target?.className,
        onScreen: r.x >= 0 && r.y >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
        below44: r.width < 44 || r.height < 44 }];
    });
    return { surfaceWidth: rect.width, top: rect.top, left: rect.left, height: rect.height,
      overflow: surface.scrollWidth > surface.clientWidth,
      centerHitInside: hit !== null && surface.contains(hit), centerHitClass: hit?.className,
      focusInside: surface.contains(document.activeElement),
      ancestorZIndices: [surface, surface.parentElement, surface.parentElement?.parentElement]
        .filter((node) => node != null).map((node) => getComputedStyle(node).zIndex), controls };
  });
  mkdirSync(AUDIT_DIR, { recursive: true });
  const file = `${auditTag(cell)}-${name}`;
  const data = { ...cell, name, screenshot: `${file}.png`, ...geometry };
  writeFileSync(path.join(AUDIT_DIR, `${file}.json`), JSON.stringify(data, null, 2));
  appendFileSync(path.join(test.info().project.outputDir, "audit-geometry.jsonl"), `${JSON.stringify(data)}\n`);
  await page.screenshot({ path: path.join(AUDIT_DIR, `${file}.png`), animations: "disabled", caret: "hide", scale: "css" });
}

for (const cell of AUDIT_CELLS) {
    const { account, language, width } = cell;
    test.describe(`menu audit ${auditTag(cell)}`, () => {
      test.afterEach(async ({ page }, info) => {
        if (info.status === info.expectedStatus || info.status === "skipped") return;
        mkdirSync(AUDIT_DIR, { recursive: true });
        const file = `${auditTag(cell)}-${info.title.replace(/[^a-z0-9-]+/gi, "-")}-failed`;
        await page.screenshot({ path: path.join(AUDIT_DIR, `${file}.png`), animations: "disabled" });
        writeFileSync(path.join(AUDIT_DIR, `${file}.txt`), await page.locator("body").innerText());
      });
      for (const surface of account === "guest" ? GUEST : REGISTERED) {
        test(surface.name, async ({ page }) => {
          test.skip(surface.minWidth !== undefined && width < surface.minWidth, "Not offered from the phone drawer");
          await openFixture(page, cell);
          await openSettings(page, cell);
          for (const [index, key] of surface.path.entries()) {
            const target = page.getByRole("button", { name: label(language, key), exact: true })
              .or(page.getByRole("menuitem", { name: label(language, key), exact: true })).last();
            if (surface.optional && index === surface.path.length - 1) {
              test.skip(await target.count() === 0, "Feature is unavailable in this release fixture");
            }
            // The delete-account row includes explanatory text in its accessible name.
            if (key === "settings.profile.delete_account") {
              await page.getByRole("button", { name: new RegExp(`^${label(language, key)}`) }).click();
            } else await target.click();
          }
          const marker = surface.marker
            ? page.getByText(label(language, surface.marker), { exact: true }).filter({ visible: true }).last()
            : surface.name === "account-delete" ? page.getByRole("dialog", { name: label(language, "settings.profile.request_deletion.title"), exact: true })
              : page.getByRole("dialog").last();
          if (surface.name === "account-delete") {
            const confirmButton = marker.getByRole("button", { name: label(language, "settings.profile.request_deletion.confirm"), exact: true });
            const hitTest = await confirmButton.evaluate((control) => {
              const rect = control.getBoundingClientRect();
              const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
              return { controlCovered: hit !== null && !control.contains(hit), coveringClass: hit?.className, coveringZIndex: hit ? getComputedStyle(hit).zIndex : null };
            });
            await test.info().attach("account-deletion-occlusion", { body: JSON.stringify(hitTest, null, 2), contentType: "application/json" });
            appendFileSync(path.join(test.info().project.outputDir, "audit-occlusion.jsonl"), `${JSON.stringify({ ...cell, ...hitTest })}\n`);
          }
          await capture(page, cell, surface.name, marker);
          if (surface.name === "feedback-general") {
            const learnMore = page.getByRole("button", { name: label(language, "common.learn_more"), exact: true });
            await learnMore.scrollIntoViewIfNeeded();
            await capture(page, cell, "feedback-footer", learnMore);
          }
        });
      }

      for (const kind of ["picker", "bug", "feature"] as const) {
        test(`feedback category ${kind}`, async ({ page }) => {
          await openFixture(page, cell);
          await openSettings(page, cell);
          if (account === "registered") {
            await button(page, cell, FEEDBACK).click();
            await button(page, cell, "feedback.type.general").click();
          } else await page.getByRole("menuitem", { name: label(language, "guest.shell.feedback"), exact: true }).click();
          await button(page, cell, "feedback.type.general").click();
          if (kind !== "picker") await button(page, cell, `feedback.type.${kind}`).click();
          await capture(page, cell, `feedback-category-${kind}`, kind === "picker"
            ? button(page, cell, "feedback.type.bug") : page.getByRole("dialog").last());
        });
      }

      if (account === "guest") {
        const authPages = [
          ["login", "/?auth=login", "auth.recovery.forgot"],
          ["signup", "/?auth=signup", "auth.signup.password_requirement"],
          ["request-access", "/?auth=request", "auth.access_request.title"],
          ["forgot-password", "/auth/forgot-password", "auth.recovery.title"],
          ["recovery", "/auth/recovery", "auth.recovery.reset_title"],
        ];
        for (const [name, url, markerKey] of authPages) {
          test(`auth ${name}`, async ({ page }) => {
            await openFixture(page, cell, url);
            await capture(page, cell, `auth-${name}`, page.getByText(label(language, markerKey), { exact: true }));
          });
        }
        for (const picker of ["menu", "language"] as const) {
          test(`auth settings ${picker}`, async ({ page }) => {
            await openFixture(page, cell, "/?auth=login");
            const trigger = page.getByRole("button", { name: label(language, "guest.shell.settings"), exact: true });
            await trigger.click();
            const languageButton = page.getByRole("menuitem", { name: label(language, "guest.shell.language"), exact: true });
            if (picker === "language") await languageButton.click();
            await capture(page, cell, `auth-settings-${picker}`, picker === "language"
              ? page.getByRole("dialog", { name: label(language, "guest.shell.language"), exact: true }) : languageButton);
            if (picker === "language") {
              await page.keyboard.press("Escape");
              const modal = page.getByRole("dialog", { name: label(language, "guest.shell.language"), exact: true });
              const escapeDismissed = await modal.count() === 0;
              if (!escapeDismissed) {
                await modal.getByRole("textbox").focus();
                for (let tab = 0; tab < 3; tab += 1) await page.keyboard.press("Tab");
              }
              const focus = await page.evaluate(() => ({
                insideDialog: document.activeElement?.closest('[role="dialog"]') !== null,
                tag: document.activeElement?.tagName,
                placeholder: document.activeElement?.getAttribute("placeholder"),
              }));
              writeFileSync(path.join(AUDIT_DIR, `${auditTag(cell)}-auth-language-interaction.json`), JSON.stringify({ ...cell, escapeDismissed, focus }, null, 2));
              if (!escapeDismissed) await page.screenshot({ path: path.join(AUDIT_DIR, `${auditTag(cell)}-auth-language-after-escape-tab.png`), animations: "disabled", caret: "hide", scale: "css" });
            }
          });
        }
        test("new chat confirmation", async ({ page }) => {
          await openFixture(page, cell);
          if (width < 720) await page.getByTestId("chat-shell-menu-trigger").click();
          await button(page, cell, "chat.new_chat").click();
          await capture(page, cell, "guest-new-chat", page.getByRole("dialog", { name: label(language, "guest.new_conversation.title"), exact: true }));
        });
      }

      if (account === "registered") {
        for (const destination of ["security", "terms", "privacy"] as const) {
          test(`settings route ${destination}`, async ({ page }) => {
            await openFixture(page, cell);
            await openSettings(page, cell);
            if (destination === "security") {
              await button(page, cell, DATA).click();
              await button(page, cell, "settings.data.security").click();
            } else {
              await button(page, cell, "settings.help.title").click();
              await page.getByRole("link", { name: label(language, `settings.help.${destination}`), exact: true }).first().click();
            }
            await expect(page).toHaveURL(new RegExp(destination === "security" ? "/account/security$" : `/${destination}$`));
            await page.addStyleTag({ content: FREEZE_CSS });
            await capture(page, cell, destination, page.getByRole("heading", { name: label(language, destination === "security" ? "account_security.title" : `legal.${destination}.title`), exact: true }));
          });
        }
        test("currency picker", async ({ page }) => {
          await openFixture(page, cell);
          await openSettings(page, cell);
          await button(page, cell, PREFS).click();
          await button(page, cell, "settings.app.home_country").click();
          await page.getByRole("button", { name: new RegExp(`^${label(language, "settings.app.currency")} `) }).click();
          await capture(page, cell, "currency", page.getByPlaceholder(label(language, "settings.app.search_currency")));
        });
        for (const picker of ["display-name", "preferred-name", "avatar", "profile-language"] as const) {
          test(`profile ${picker}`, async ({ page }) => {
            await openFixture(page, cell);
            await openSettings(page, cell);
            await button(page, cell, "settings.profile.title").click();
            const dialog = page.getByRole("dialog", { name: label(language, "settings.profile.title"), exact: true });
            await expect(dialog.getByText("Alexandra Featherstonehaugh", { exact: true })).toBeVisible();
            let marker: Locator;
            if (picker === "display-name") {
              await button(page, cell, "settings.profile.edit_display_name").click();
              marker = dialog.getByRole("textbox");
            } else if (picker === "preferred-name") {
              await page.locator("#argus-profile-preferred-name").click();
              marker = dialog.getByRole("textbox");
            } else if (picker === "avatar") {
              await page.locator("[data-avatar-theme-trigger]").click();
              marker = dialog.getByRole("radiogroup");
            } else {
              await page.locator("#argus-profile-language-trigger").click();
              marker = dialog.getByRole("listbox");
            }
            await capture(page, cell, picker, marker);
          });
        }
        for (const action of ["menu", "rename", "delete"] as const) {
          test(`header ${action}`, async ({ page }) => {
            await openFixture(page, cell);
            await button(page, cell, "chat.chat_options").click();
            let marker = page.getByRole("menu");
            if (action !== "menu") {
              await page.getByRole("menuitem", { name: label(language, action === "rename" ? "chat.rename_chat" : "chat.delete_chat"), exact: true }).click();
              marker = action === "rename" ? page.locator('input[maxlength="80"]') : page.getByRole("alertdialog");
            }
            await capture(page, cell, `header-${action}`, marker);
          });
        }
        test("recents row menu", async ({ page }) => {
          await openFixture(page, cell);
          if (width < 720) await page.getByTestId("chat-shell-menu-trigger").click();
          await button(page, cell, "common.recents").click();
          await page.locator("button[data-actions]").first().click();
          await capture(page, cell, "recents-menu", page.getByRole("menu"));
        });
      }

      test("assistant more", async ({ page }) => {
        await openFixture(page, cell);
        await page.route("**/api/v1/conversations/*/messages*", (route) => route.request().method() === "GET" ? route.fulfill({
          json: { items: [{ id: "phone-assistant", role: "assistant", content: language === "en" ? "Your idea is ready to review." : "Tu idea está lista para revisar.", created_at: "2026-08-01T12:00:00Z", metadata: {} }], next_cursor: null },
        }) : route.fallback());
        await page.reload({ waitUntil: "networkidle" });
        await page.addStyleTag({ content: FREEZE_CSS });
        await button(page, cell, "chat.more_actions").click();
        await capture(page, cell, "assistant-more", page.getByRole("menu"));
      });
    });
  }
