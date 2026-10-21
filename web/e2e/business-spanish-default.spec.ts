import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture, type Language } from "./support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "./support/month-close-wire";

const english = JSON.parse(readFileSync("public/locales/en/common.json", "utf-8"));
const en = (key: string, count?: number): string => {
  const value = key.split(".").reduce((node, part) => node?.[part], english);
  return String(value).replace("{{count}}", String(count));
};

async function installAccount(page: Page, language: Language) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await page.addInitScript(() => {
    Object.assign(window, { __deviceLanguage: window.localStorage.getItem("i18nextLng") });
  });
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  await page.addInitScript(() => {
    const device = (window as Window & { __deviceLanguage?: string | null }).__deviceLanguage ?? null;
    if (device === null) window.localStorage.removeItem("i18nextLng");
    else window.localStorage.setItem("i18nextLng", device);
  });
}

async function setup(page: Page, language: Language) {
  await installAccount(page, language);
  await page.addInitScript(() => {
    const seen: string[] = [];
    const current = () => document.documentElement.lang;
    seen.push(current());
    new MutationObserver(() => seen.push(current())).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["lang"],
    });
    Object.assign(window, { __businessLangs: seen });
  });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  const receipt = await source.receipt("rcpt-ferreteria");
  const activity = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 1, needs_attention_count: 0 };
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: await source.workspace() });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "My business" } });
    if (path === "spaces") {
      const spaces = (await source.spaces()).slice(0, 1).map((space) => ({ ...space, name: "My business" }));
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
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}

test("an en-US browser with nothing stored and a Spanish account opens Business in Spanish", async ({ page }) => {
  await setup(page, "es-419");
  const response = await page.goto("/biz");
  const html = await response?.text();
  expect(html ?? "").toMatch(/<html[^>]*\slang="es"/);
  expect(html ?? "").not.toMatch(/<html[^>]*\slang="en"/);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const langs = await page.evaluate(() => (window as Window & { __businessLangs?: string[] }).__businessLangs ?? []);
  expect(langs.every((lang) => lang === "es")).toBe(true);
  const overview = page.locator("#business-overview-title");
  await expect(overview).toHaveText("Hola");
  await expect(page.getByTestId("month-close-task-review")).toContainText("Revisa 1 recibo en la Bandeja");
  await expect(page.getByTestId("month-close-task-review").getByRole("button", { name: "Revisar" })).toBeVisible();
  await expect(page.getByTestId("business-sidebar-nav")).toContainText("Inicio");
  await expect(page.getByTestId("business-sidebar-nav")).toContainText("Bandeja");
  await expect(page.getByTestId("business-primary-upload")).toHaveText("Agregar");
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

  await page.getByTestId("month-close-task-review").getByRole("button", { name: "Revisar" }).click();
  await page.getByTestId("business-inbox-receipts").getByRole("button", { name: /Ferretería La Esquina/ }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const review = page.getByTestId("side-drawer");
  await expect(review).toContainText("Comercio o persona");
  await expect(review).toContainText("Fecha de actividad");
  await expect(review).toContainText("Categoría");
  await expect(review).toContainText("Moneda");
  await expect(review).toContainText("Pagado desde");
  await expect(review).not.toContainText("Merchant");
  await expect(review).not.toContainText("Paid from");
});

test("an English account opens Business in English", async ({ page }) => {
  await setup(page, "en");
  await page.goto("/biz");
  await expect(page.locator("#business-overview-title")).toHaveText(en("business.overview.greeting_unnamed"));
  const task = page.getByTestId("month-close-task-review");
  await expect(task).toContainText(en("business.month_close.checklist_review_one", 1));
  await expect(task.getByRole("button", { name: en("business.month_close.action_review") })).toBeVisible();
  await expect(page.getByTestId("business-sidebar-nav")).toContainText(en("business.nav.overview"));
  await expect(page.getByTestId("business-sidebar-nav")).toContainText(en("business.nav.inbox"));
  await expect(page.getByTestId("business-primary-upload")).toHaveText(en("business.actions.add"));
  await expect(page.getByTestId("amounts-toggle")).toHaveAccessibleName(en("business.amounts.hide"));
  for (const spanish of ["Hola", "Inicio", "Bandeja", "Agregar", "Ocultar montos"]) {
    await expect(page.getByText(spanish, { exact: true })).toHaveCount(0);
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

  await task.getByRole("button", { name: en("business.month_close.action_review") }).click();
  await page.getByTestId("business-inbox-receipts").getByRole("button", { name: /Ferretería La Esquina/ }).click();
  const review = page.getByTestId("side-drawer");
  await expect(review).toContainText(en("business.dossier.field.counterparty"));
  await expect(review).toContainText(en("business.dossier.field.occurred_on"));
  await expect(review).toContainText(en("business.review.category"));
  await expect(review).toContainText(en("business.review.currency"));
  await expect(review).toContainText(en("business.review.account"));
  await expect(review).not.toContainText("Comercio o persona");
  await expect(review).not.toContainText("Pagado desde");
});

test("an en-US browser with nothing stored sees a Spanish sign-in and can choose English, which a reload keeps", async ({ page }) => {
  await installAccount(page, "es-419");
  await page.goto("/?preview=true");
  const switcher = page.getByTestId("auth-language-switch");
  await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toBeVisible();
  await expect(switcher.getByRole("button")).toHaveText(["English"]);
  await switcher.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toHaveCount(0);
  await expect(switcher.getByRole("button")).toHaveText(["Español"]);
  await page.reload();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  await expect(switcher.getByRole("button")).toHaveText(["Español"]);
});
