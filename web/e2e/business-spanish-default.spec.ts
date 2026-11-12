import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { ProfilePatch, UserResponse } from "../lib/argus-api";
import type { BusinessAccount } from "../lib/business-api";
import { createDossierFixtures, dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { greetingPeriod } from "../components/business-app/foundation/home-greeting";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture, type Language } from "./support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "./support/month-close-wire";

const english = JSON.parse(readFileSync("public/locales/en/common.json", "utf-8"));
const spanish = JSON.parse(readFileSync("public/locales/es-419/common.json", "utf-8"));
const phrase = (table: unknown, key: string, count?: number): string => {
  const value = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], table);
  return String(value).replace("{{count}}", String(count));
};
const en = (key: string, count?: number) => phrase(english, key, count);
const es = (key: string, count?: number) => phrase(spanish, key, count);
// 09:00 local is morning in home-greeting.ts. The page clock stays there, so the greeting cannot follow the runner's hour.
const PINNED_AT = new Date(2026, 9, 25, 9, 0, 0);
const PINNED_PERIOD = greetingPeriod(PINNED_AT.getHours());
const spanishGreeting = es(`business.overview.greetings.${PINNED_PERIOD}`);
const englishGreeting = en(`business.overview.greetings.${PINNED_PERIOD}`);
const BUSINESS_NAME = "Ferretería Los Pinos";
const dossierAccount: BusinessAccount = { id: "acct-fixture", nickname: "Caja", type: "cash", currency: "DOP" };
const dossiers = createDossierFixtures([dossierAccount]);

async function installAccount(page: Page, language: Language, options: { languageChosen?: boolean } = {}) {
  await page.clock.setFixedTime(PINNED_AT);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await page.addInitScript(() => {
    Object.assign(window, { __deviceLanguage: window.localStorage.getItem("i18nextLng") });
  });
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true, ...options });
  await page.addInitScript(() => {
    const device = (window as Window & { __deviceLanguage?: string | null }).__deviceLanguage ?? null;
    if (device === null) window.localStorage.removeItem("i18nextLng");
    else window.localStorage.setItem("i18nextLng", device);
  });
}

type Painted = { langs: string[]; texts: string[] };

/** Every lang the document took and every text node it ever held, from the first parsed byte, so a word replaced before the next frame still counts. */
async function recordPaint(page: Page) {
  await page.addInitScript(() => {
    const painted: Painted = { langs: [], texts: [] };
    const keep = (text: string | null | undefined) => { const trimmed = text?.trim(); if (trimmed) painted.texts.push(trimmed); };
    const keepTree = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) return keep(node.nodeValue);
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) keep(walker.currentNode.nodeValue);
    };
    new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "attributes") painted.langs.push(document.documentElement.lang);
        if (record.type === "characterData") { keep(record.oldValue); keep(record.target.nodeValue); }
        record.addedNodes.forEach((node) => {
          if (node === document.documentElement) painted.langs.push(document.documentElement.lang);
          keepTree(node);
        });
      }
    }).observe(document, { subtree: true, childList: true, characterData: true, characterDataOldValue: true, attributes: true, attributeFilter: ["lang"] });
    Object.assign(window, { __painted: painted });
  });
}

const paintedSoFar = (page: Page) => page.evaluate(() => (window as Window & { __painted?: Painted }).__painted ?? null);

async function setup(page: Page, language: Language, options: { languageChosen?: boolean } = {}) {
  await installAccount(page, language, options);
  await recordPaint(page);
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipt = await source.receipt("rcpt-ferreteria");
  const activity = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 1, ready_to_review_count: 1, needs_attention_count: 0 };
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: BUSINESS_NAME } });
    if (path === "spaces") {
      const spaces = (await source.spaces()).slice(0, 1).map((space) => ({ ...space, name: BUSINESS_NAME }));
      return route.fulfill({ json: { spaces } });
    }
    if (path === "overview") return route.fulfill({ json: { ...await source.overview("2026-10-01", "2026-10-31"), totals: [], fiscal_totals: [], without_fiscal_totals: [] } });
    if (path === "receipts") return route.fulfill({ json: { items: url.searchParams.get("view") === "all" ? [receipt] : [receipt], activity } });
    if (path === `receipts/${receipt.id}`) return route.fulfill({ json: receipt });
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (["email/deliveries", "captures"].includes(path)) return route.fulfill({ json: { items: [] } });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    if (path === "month-close") return route.fulfill({ json: monthCloseWire(url.searchParams.get("month") ?? "2026-10") });
    if (path === "open-items") return route.fulfill({ json: OPEN_ITEMS_WIRE });
    if (/^drafts\/[^/]+\/dossier$/.test(path) && route.request().method() === "GET") return route.fulfill({ json: await dossiers.dossier(dossierFixtureIds.unknown) });
    if (path === "fiscal-profile/fields") return route.fulfill({ json: await dossiers.dgiiFields() });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}

async function openAccountWithPersistence(page: Page) {
  await setup(page, "es-419");
  const initialProfile = page.waitForResponse((response) =>
    response.request().method() === "GET" && new URL(response.url()).pathname === "/api/v1/me",
  );
  await page.goto("/biz");
  let account: UserResponse = await (await initialProfile).json();
  const patches: ProfilePatch[] = [];
  const serveAccount = async (route: Route) => {
    if (route.request().method() === "PATCH") {
      const patch: ProfilePatch = route.request().postDataJSON();
      patches.push(patch);
      account = {
        ...account,
        user: { ...account.user, ...patch, onboarding: { ...account.user.onboarding, language_confirmed: true } },
      };
    } else {
      expect(route.request().method()).toBe("GET");
    }
    return route.fulfill({ json: account });
  };
  await page.route("**/api/v1/me", serveAccount);
  return { patches, serveAccount };
}

test("an en-US browser with nothing stored and a Spanish account opens Business in Spanish", async ({ page }) => {
  await setup(page, "es-419");
  const response = await page.goto("/biz");
  const html = await response?.text();
  expect(html ?? "").toMatch(/<html[^>]*\slang="es"/);
  expect(html ?? "").not.toMatch(/<html[^>]*\slang="en"/);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const overview = page.locator("#business-overview-title");
  await expect(overview).toHaveText(spanishGreeting);
  await expect(page.getByTestId("business-sidebar-nav")).toContainText("Inicio");
  await expect(page.getByTestId("business-sidebar-nav")).toContainText("Bandeja");
  await expect(page.getByTestId("business-primary-upload")).toHaveText("Agregar");
  const painted = await paintedSoFar(page);
  expect(painted, "the paint recorder ran from the first byte").not.toBeNull();
  expect(painted!.langs, "the document was seen with a lang").toContain("es");
  expect(painted!.langs.filter((lang) => lang !== "es"), "the document never took another lang").toEqual([]);
  for (const word of [spanishGreeting, "Inicio", "Bandeja", "Agregar"]) expect(painted!.texts, `${word} painted`).toContain(word);
  const firstScreenEnglish = [`business.overview.greetings.${PINNED_PERIOD}`, "business.overview.greeting_unnamed", "business.nav.overview", "business.nav.inbox", "business.nav.transactions", "business.actions.add", "business.month_close.action_review"].map((key) => en(key));
  expect(painted!.texts.filter((text) => firstScreenEnglish.includes(text)), "no English word painted before Spanish").toEqual([]);
  await expect(page.getByRole("heading", { name: es("business.inicio.attention.title") })).toBeVisible();
  await expect(page.getByTestId("amounts-toggle")).toHaveAccessibleName("Ocultar montos");
  for (const english of ["Upload receipts", "My business", "Record expense", "Open inbox", "Add", "Overview", "Inbox", "Hide amounts"]) {
    await expect(page.getByText(english, { exact: true })).toHaveCount(0);
  }

  await page.getByTestId("business-primary-upload").click();
  const upload = page.getByRole("dialog", { name: "Agregar" });
  await expect(upload).toBeVisible();
  await expect(upload).not.toContainText("Upload receipt");
  await expect(upload.getByTestId("intake-choose")).toHaveText("Elegir archivos");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByTestId("business-primary-upload").click();
  await page.getByTestId("intake-write-open").click();
  const record = page.getByRole("dialog");
  await expect(record.getByTestId("intake-write")).toBeVisible();
  await expect(record).toContainText("Escríbelo");
  await expect(record).not.toContainText("Write it");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByRole("button", { name: /Ferretería La Esquina/ }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const review = page.getByTestId("side-drawer");
  await expect(review).toContainText("Contraparte");
  await expect(review).toContainText("Fecha del comprobante");
  await expect(review).toContainText("Categoría");
  await expect(review).toContainText("Moneda");
  await expect(review).toContainText("Cómo se pagó");
  await expect(review).not.toContainText("Merchant");
  await expect(review).not.toContainText("Paid from");
  await expect(review).not.toContainText("How it was paid");
});

test("an English account opens Business in English", async ({ page }) => {
  await setup(page, "en");
  await page.goto("/biz");
  await expect(page.locator("#business-overview-title")).toHaveText(englishGreeting);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { name: en("business.inicio.attention.title") })).toBeVisible();
  await expect(page.getByTestId("business-sidebar-nav")).toContainText(en("business.nav.overview"));
  await expect(page.getByTestId("business-sidebar-nav")).toContainText(en("business.nav.inbox"));
  await expect(page.getByTestId("business-primary-upload")).toHaveText(en("business.actions.add"));
  await expect(page.getByTestId("amounts-toggle")).toHaveAccessibleName(en("business.amounts.hide"));
  for (const word of [spanishGreeting, "Hola", "Inicio", "Bandeja", "Agregar", "Ocultar montos"]) {
    await expect(page.getByText(word, { exact: true })).toHaveCount(0);
  }

  await page.getByTestId("business-primary-upload").click();
  const upload = page.getByRole("dialog", { name: en("business.intake.add_title") });
  await expect(upload).toBeVisible();
  await expect(upload.getByTestId("intake-choose")).toHaveText(en("business.intake.choose_multiple"));
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByTestId("business-primary-upload").click();
  await page.getByTestId("intake-write-open").click();
  await expect(page.getByRole("dialog")).toContainText(en("business.intake.write"));
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByRole("button", { name: /Ferretería La Esquina/ }).click();
  const review = page.getByTestId("side-drawer");
  await expect(review).toContainText(en("business.dossier.field.counterparty"));
  await expect(review).toContainText(en("business.dossier.field.occurred_on"));
  await expect(review).toContainText(en("business.dossier.field.category_id"));
  await expect(review).toContainText(en("business.review.currency"));
  await expect(review).toContainText("How it was paid");
  await expect(review).not.toContainText("Contraparte");
  await expect(review).not.toContainText("Pagado desde");
});

test("an English account on a device that last showed English keeps the page in English", async ({ page }) => {
  await setup(page, "en");
  await page.addInitScript(() => window.localStorage.setItem("i18nextLng", "en"));
  await page.goto("/biz");
  await expect(page.locator("#business-overview-title")).toHaveText(englishGreeting);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  const painted = await paintedSoFar(page);
  const sinceEnglish = painted!.langs.slice(painted!.langs.indexOf("en"));
  expect(sinceEnglish.filter((lang) => lang !== "en"), "once English shows, the document stays en").toEqual([]);
});

test("an en-US browser with nothing stored sees a Spanish sign-in and can choose English, which a reload keeps", async ({ page }) => {
  await installAccount(page, "es-419");
  await page.goto("/?preview=true");
  const switcher = page.getByTestId("auth-language-switch");
  await expect(page.getByRole("heading", { name: es("auth.login.title") })).toBeVisible();
  await expect(page.getByRole("button", { name: es("auth.login.submit"), exact: true })).toBeVisible();
  await expect(switcher.getByRole("button")).toHaveText(["English"]);
  await switcher.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: en("auth.login.title") })).toBeVisible();
  await expect(page.getByRole("button", { name: en("auth.login.submit"), exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: es("auth.login.submit"), exact: true })).toHaveCount(0);
  await expect(switcher.getByRole("button")).toHaveText(["Español"]);
  await page.reload();
  await expect(page.getByRole("heading", { name: en("auth.login.title") })).toBeVisible();
  await expect(page.getByRole("button", { name: en("auth.login.submit"), exact: true })).toBeVisible();
  await expect(switcher.getByRole("button")).toHaveText(["Español"]);
});

test("Preferencias > Idioma switches a Spanish account to English in place and saves it on the account", async ({ page }) => {
  const { patches } = await openAccountWithPersistence(page);
  await expect(page.locator("#business-overview-title")).toHaveText(spanishGreeting);
  const loaded = await page.evaluate(() => performance.getEntriesByType("navigation").length);

  await page.getByTestId("header-profile-trigger").click();
  await page.getByTestId("profile-menu-settings").click();
  await page.getByRole("button", { name: "Idioma de la app", exact: true }).click();
  await page.getByRole("radio", { name: "English", exact: true }).click();

  await expect(page.locator("#business-overview-title")).toHaveText(englishGreeting);
  await expect(page.getByTestId("business-sidebar-nav")).toContainText(en("business.nav.inbox"));
  await expect.poll(() => patches).toEqual([{ language: "en", locale: "en-US" }]);
  expect(await page.evaluate(() => performance.getEntriesByType("navigation").length)).toBe(loaded);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("main[lang]")).toHaveCount(0);
});

test("an account that never chose a language, saved as en by default, opens Business in Spanish", async ({ page }) => {
  await setup(page, "en", { languageChosen: false });
  await page.goto("/biz");
  await expect(page.locator("#business-overview-title")).toHaveText(spanishGreeting);
  await expect(page.getByTestId("business-sidebar-nav")).toContainText("Bandeja");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(page.getByText(englishGreeting, { exact: true })).toHaveCount(0);
  await expect(page.getByText(en("business.overview.greeting_unnamed"), { exact: true })).toHaveCount(0);
});

test("English chosen in Preferencias is saved on the account and wins on another device", async ({ browser }) => {
  const first = await browser.newContext();
  const page = await first.newPage();
  const { patches, serveAccount } = await openAccountWithPersistence(page);
  await page.getByTestId("header-profile-trigger").click();
  await page.getByTestId("profile-menu-settings").click();
  await page.getByRole("button", { name: "Idioma de la app", exact: true }).click();
  await page.getByRole("radio", { name: "English", exact: true }).click();
  await expect(page.locator("#business-overview-title")).toHaveText(englishGreeting);
  await expect.poll(() => patches).toEqual([{ language: "en", locale: "en-US" }]);
  await first.close();

  const other = await browser.newContext();
  const elsewhere = await other.newPage();
  expect(await other.storageState()).toEqual({ cookies: [], origins: [] });
  await setup(elsewhere, "es-419");
  await elsewhere.route("**/api/v1/me", serveAccount);
  const savedProfile = elsewhere.waitForResponse((response) =>
    response.request().method() === "GET" && new URL(response.url()).pathname === "/api/v1/me",
  );
  await elsewhere.goto("/biz");
  expect((await (await savedProfile).json()).user).toMatchObject({
    language: "en", locale: "en-US", onboarding: { language_confirmed: true },
  });
  await expect(elsewhere.locator("#business-overview-title")).toHaveText(englishGreeting);
  await expect(elsewhere.getByTestId("business-sidebar-nav")).toContainText(en("business.nav.inbox"));
  expect(patches).toEqual([{ language: "en", locale: "en-US" }]);
  await other.close();
});
