import { expect, test, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import reportAnswer from "../test-fixtures/records-default-report-answer.json";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { FREEZE_CSS, fulfillAcceptedBusinessConsent, installBreakpointFixture, type Language } from "./support/breakpoint-fixture";
import { monthCloseWire, OPEN_ITEMS_WIRE } from "./support/month-close-wire";

const baseline = process.env.CUADRAO_ADD_BASELINE === "true";
const evidence = process.env.CUADRAO_ADD_EVIDENCE_DIR;

async function setup(page: Page, language: Language, emailAvailable = false) {
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/business/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.split("/business/")[1];
    if (path === "workspace") return route.fulfill({ json: { ...await source.workspace(), receiving_channels: { email: { available: emailAvailable }, whatsapp: { available: false } } } });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "receipts") return route.fulfill({ json: { items: [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, needs_attention_count: 0 } } });
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: true, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: true, receiving_address: "recibos@example.test" } });
    if (["email/deliveries", "captures"].includes(path)) return route.fulfill({ json: { items: [] } });
    if (path === "report-views") return route.fulfill({ json: [] });
    if (path === "reports/query") return route.fulfill({ json: reportAnswer });
    if (path === "reports/export") return route.fulfill({ contentType: "application/zip", headers: { "Content-Disposition": 'attachment; filename="registros.zip"' }, body: "synthetic archive" });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    if (path === "month-close") return route.fulfill({ json: monthCloseWire(url.searchParams.get("month") ?? "2026-10") });
    if (path === "open-items") return route.fulfill({ json: OPEN_ITEMS_WIRE });
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
}

for (const language of ["es-419", "en"] as const) {
  for (const width of [1280, 390]) {
    test(`single add action ${language} ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await setup(page, language);
      for (const view of ["overview", "transactions"] as const) {
        await page.goto(view === "overview" ? "/biz" : "/biz?view=transactions");
        const add = page.getByTestId("business-primary-upload");
        await expect(add).toBeVisible();
        if (view === "transactions") await expect(page.locator("[data-report-connected]")).toBeVisible();
        else await expect(page.getByTestId("month-close-cards")).toBeVisible();
        await page.addStyleTag({ content: FREEZE_CSS });
        if (evidence) {
          const name = `${evidence}/${baseline ? "before" : "after"}-${view}-${language}-${width}`;
          await page.screenshot({ path: `${name}.png`, fullPage: true });
          const metrics = await add.evaluate((button) => {
            const rect = (element: Element) => { const { x, y, width, height, right } = element.getBoundingClientRect(); return { x, y, width, height, right }; };
            const pill = button.parentElement!;
            const row = pill.parentElement!;
            const style = getComputedStyle(button);
            return { button: rect(button), pill: rect(pill), row: rect(row), padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft], gap: getComputedStyle(row).gap, order: [...row.children].map((child) => child.getAttribute("data-testid") ?? child.tagName) };
          });
          writeFileSync(`${name}.json`, JSON.stringify(metrics, null, 2));
        }
        if (baseline) continue;
        await expect(page.getByTestId("add-menu-more")).toHaveCount(0);
        await expect(page.getByRole("menu")).toHaveCount(0);
        await expect(add.locator("..").getByRole("button")).toHaveCount(1);
        await expect(add.locator("..").locator("svg.lucide-chevron-down")).toHaveCount(0);
        const box = await add.boundingBox();
        expect(box!.width).toBeLessThan(160);
        expect(box!.height).toBe(44);
        await add.focus();
        await page.keyboard.press("Tab");
        await expect(add.locator("..").locator(":focus")).toHaveCount(0);
        if (view === "transactions") {
          const download = page.waitForEvent("download");
          await page.getByTestId("records-export").click();
          expect((await download).suggestedFilename()).toMatch(/\.zip$/);
        }
      }
    });
  }
}

for (const activation of ["click", "Enter", "Space", "shortcut"] as const) {
  test(`Agregar opens upload with ${activation}`, async ({ page }) => {
    test.skip(baseline);
    await setup(page, "es-419");
    await page.goto("/biz");
    const add = page.getByTestId("business-primary-upload");
    await expect(add).toBeVisible();
    await expect(page.getByTestId("month-close-cards")).toBeVisible();
    if (activation === "click") await add.click();
    else if (activation === "shortcut") { await page.locator("body").click({ position: { x: 1, y: 1 } }); const command = await page.evaluate(() => /Mac|iPhone|iPad|iPod/.test(navigator.userAgent)); await page.keyboard.press(`${command ? "Meta" : "Control"}+Shift+Period`); }
    else { await add.focus(); await page.keyboard.press(activation); }
    await expect(page.getByRole("dialog", { name: "Agregar", exact: true })).toBeVisible();
    await expect(page.getByTestId("intake-choose")).toBeVisible();
  });
}

test("email availability restores only the copy item", async ({ page }) => {
  test.skip(baseline);
  await setup(page, "es-419", true);
  await page.goto("/biz");
  const trigger = page.getByTestId("add-menu-more");
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(page.getByRole("menuitem")).toHaveCount(1);
  await expect(page.getByRole("menuitem")).toHaveText("Copiar dirección de reenvío");
});
