import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { createBusinessReportHttpFixture } from "../__tests__/fixtures/business-report-http-fixture";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture, type Language, type Theme } from "./support/breakpoint-fixture";
import { fulfillSyntheticBusinessFallback } from "./support/synthetic-business-fallback";

async function open606(page: Page) {
  const fixture = createBusinessReportHttpFixture();
  const purchases = fixture.records.filter((row) => row.family === "purchase");
  purchases.forEach((row) => { row.currency = "DOP"; row.fiscal_data = "complete"; row.stage = "ready_for_export"; });
  purchases[0].fiscal_data = "missing";
  purchases[0].ready = false;
  purchases[0].missing = ["expense_type_missing"];
  purchases[0].stage = "needs_fiscal_data";
  purchases[1].currency = "USD";
  fixture.controls.rncSuppliers = Array.from({ length: 12 }, (_, index) => ({
    name: `Proveedor sintético ${String(index + 1).padStart(2, "0")}`,
    rnc: `1310000${String(index + 1).padStart(2, "0")}`,
    estado: "SUSPENDIDO",
    status: index % 2 ? "rnc_unverified" : "rnc_inactive",
    record_count: 1,
  }));
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (/\/(reports\/|report-views(?:\/|$))/.test(path)) {
      const response = await fixture.request(request.url(), { method: request.method(), headers: request.headers(), body: request.postData() ?? undefined });
      return route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) });
    }
    return fulfillSyntheticBusinessFallback(route, { fulfillConsent: () => fulfillAcceptedBusinessConsent(route) });
  });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.fallback() : route.abort("blockedbyclient"));
  await page.goto("/biz?view=transactions");
  await page.getByTestId("records-export").click();
  const download = page.getByTestId("records-export-download");
  await expect(download).toBeEnabled();
  await page.getByTestId("records-export-mode-dgii").getByRole("radio").check();
  await expect(page.getByTestId("records-export-rnc-notice")).toBeVisible();
  return { download, fixture };
}

async function inlineAction(link: Locator) {
  const geometry = await link.evaluate((button) => {
    const paragraph = button.closest("p")!;
    const before = document.createRange();
    before.setStart(paragraph, 0);
    before.setEndBefore(button);
    const sentence = Array.from(before.getClientRects()).at(-1)!;
    const action = button.getBoundingClientRect();
    const style = getComputedStyle(button);
    return {
      parent: paragraph.tagName,
      paragraphDisplay: getComputedStyle(paragraph).display,
      display: style.display,
      fontSize: style.fontSize,
      paragraphFontSize: getComputedStyle(paragraph).fontSize,
      padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft],
      height: action.height,
      lineHeight: Number.parseFloat(style.lineHeight),
      sentenceTop: sentence.top,
      actionTop: action.top,
    };
  });
  expect(geometry.parent).toBe("P");
  expect(geometry.paragraphDisplay).toBe("block");
  expect(["inline", "inline-block"]).toContain(geometry.display);
  expect(geometry.fontSize).toBe("14px");
  expect(geometry.paragraphFontSize).toBe("14px");
  expect(geometry.padding).toEqual(["0px", "0px", "0px", "0px"]);
  expect(geometry.height).toBeLessThanOrEqual(geometry.lineHeight + 1);
  expect(Math.abs(geometry.sentenceTop - geometry.actionTop)).toBeLessThanOrEqual(3);
}

async function fullyVisible(download: Locator, page: Page) {
  await expect(download).toBeEnabled();
  await expect(download).toBeInViewport({ ratio: 1 });
  const box = await download.boundingBox();
  expect(box).not.toBeNull();
  const viewport = page.viewportSize()!;
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
  test(`606 keeps 12 suppliers in a bordered scroll box with export visible at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const { download, fixture } = await open606(page);
    const notice = page.getByTestId("records-export-rnc-notice");
    const toggle = page.getByTestId("records-export-rnc-toggle");
    const review = page.getByTestId("records-export-notices").getByRole("button", { name: "Revisar", exact: true });
    await inlineAction(toggle);
    await inlineAction(review);
    const rows = await page.getByTestId("records-export-notices").locator(":scope > li").evaluateAll((notices) => notices.map((row) => {
      const icon = row.querySelector("svg")!.getBoundingClientRect();
      const paragraph = row.querySelector("p")!.getBoundingClientRect();
      return { iconTop: icon.top, paragraphTop: paragraph.top };
    }));
    expect(rows).toHaveLength(3);
    for (const row of rows) expect(Math.abs(row.iconTop - row.paragraphTop)).toBeLessThanOrEqual(3);
    const subtextGap = await notice.locator("p").evaluateAll(([title, body]) => body.getBoundingClientRect().top - title.getBoundingClientRect().bottom);
    expect(Math.abs(subtextGap)).toBeLessThanOrEqual(1);
    await fullyVisible(download, page);
    await toggle.click();
    await expect(toggle).toHaveText("Ocultar");
    await inlineAction(toggle);
    const list = page.getByTestId("records-export-rnc-suppliers");
    await expect(list).toBeVisible();
    await expect(list).toHaveAttribute("tabindex", "0");
    await expect(list).toHaveAttribute("aria-label", "Ver proveedores");
    await expect(list.locator(":scope > li")).toHaveCount(12);
    const scroll = await list.evaluate((element) => {
      const style = getComputedStyle(element);
      return { scrollHeight: element.scrollHeight, clientHeight: element.clientHeight, maxHeight: Number.parseFloat(style.maxHeight), height: element.getBoundingClientRect().height, overflow: style.overflowY, borders: [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth].map(Number.parseFloat) };
    });
    expect(scroll.scrollHeight).toBeGreaterThan(scroll.clientHeight);
    expect(scroll.maxHeight).toBeLessThanOrEqual(132);
    expect(scroll.height).toBeLessThanOrEqual(132);
    expect(scroll.overflow).toBe("auto");
    for (const border of scroll.borders) expect(border).toBeGreaterThan(0);
    const first = list.locator(":scope > li").first();
    await expect(first.locator(":scope > div > span").first()).toHaveText("Proveedor sintético 01");
    await expect(first.locator(":scope > div > span").last()).toHaveText("No activo");
    await expect(list.locator(":scope > li").nth(1).locator(":scope > div > span").last()).toHaveText("Sin verificar");
    await expect(first.locator(":scope > span")).toHaveText(fixture.controls.rncSuppliers[0].rnc);
    await expect(first.locator(":scope > div > span").last().locator("span").first()).toHaveCSS("background-color", "rgb(246, 235, 212)");
    await expect(list.locator(":scope > li").nth(1).locator(":scope > div > span").last().locator("span")).toHaveCSS("background-color", "rgb(237, 236, 230)");
    const supplier = await first.evaluate((element) => {
      const line = element.firstElementChild!;
      const name = line.firstElementChild!.getBoundingClientRect();
      const status = line.lastElementChild!.getBoundingClientRect();
      const rnc = element.lastElementChild!;
      return { nameTop: name.top, statusTop: status.top, statusRight: status.right, lineRight: line.getBoundingClientRect().right, rncTop: rnc.getBoundingClientRect().top, nameBottom: name.bottom, font: getComputedStyle(rnc).fontFamily, statusColor: getComputedStyle(line.lastElementChild!.firstElementChild!).color, nameColor: getComputedStyle(line.firstElementChild!).color };
    });
    expect(supplier.nameTop).toBe(supplier.statusTop);
    expect(supplier.statusRight).toBe(supplier.lineRight);
    expect(supplier.rncTop).toBeGreaterThanOrEqual(supplier.nameBottom);
    expect(supplier.font).toContain("monospace");
    expect(supplier.statusColor).not.toBe(supplier.nameColor);
    await fullyVisible(download, page);
    await list.hover();
    await page.mouse.wheel(0, 180);
    await expect.poll(() => list.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    await list.evaluate((element) => { element.scrollTop = 0; });
    await list.focus();
    await page.keyboard.press("End");
    await expect.poll(() => list.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    await fullyVisible(download, page);
    await toggle.click();
    await expect(list).toBeHidden();
    await expect(toggle).toHaveText("Ver proveedores");
    await fullyVisible(download, page);
  });
}

async function openReadinessRecords(page: Page, language: Language = "es-419", theme: Theme = "light", targetExpense = false) {
  const fixture = createBusinessReportHttpFixture();
  const purchases = fixture.records.filter((row) => row.family === "purchase");
  purchases[0].ready = false;
  purchases[0].missing = ["expense_type_missing", "payment_method_missing", "rnc_missing"];
  purchases[0].stage = "ready_for_export";
  purchases[1].ready = true;
  purchases[1].technical_state = null;
  purchases[1].report_date = "2026-10-20";
  purchases[1].currency = "DOP";
  purchases[1].gross_amount = "100.00";
  purchases[1].missing = ["ncf_missing"];
  purchases[1].stage = "needs_fiscal_data";
  purchases[2].ready = false;
  purchases[2].missing = ["ncf_missing"];
  if (targetExpense) {
    purchases[0].draft_id = null;
    purchases[0].row_id = `expense:${purchases[0].linked_activity_ids[0]}`;
  }
  await installBreakpointFixture(page, { language, theme, emptyChat: true });
  await page.route("**/api/v1/business/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (targetExpense && path.endsWith(`/expenses/${purchases[0].linked_activity_ids[0]}`)) {
      return route.fulfill({ json: {
        id: purchases[0].linked_activity_ids[0], merchant: "Registro sintético", amount: "100.00", currency: "DOP",
        category_id: null, account_id: null, occurred_on: "2026-10-01", receipt_id: null, draft_id: null,
        recorded_at: "2026-10-01T12:00:00Z", revision: 1,
      } });
    }
    if (/\/(reports\/|report-views(?:\/|$))/.test(path)) {
      const response = await fixture.request(request.url(), { method: request.method(), headers: request.headers(), body: request.postData() ?? undefined });
      if (path.endsWith("/reports/query")) {
        const answer = await response.json();
        // A deliberately different count proves the card renders the server aggregate.
        answer.overview.not_ready = 17;
        return route.fulfill({ status: response.status, json: answer });
      }
      return route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) });
    }
    return fulfillSyntheticBusinessFallback(route, { fulfillConsent: () => fulfillAcceptedBusinessConsent(route) });
  });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.fallback() : route.abort("blockedbyclient"));
  await page.goto("/biz?view=transactions");
  await expect(page.getByTestId("transacciones-records")).toBeVisible();
  return fixture;
}

for (const language of ["es-419", "en"] as const) {
  test(`server readiness, reasons, filter, and all row heights in ${language}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const fixture = await openReadinessRecords(page, language);
    const spanish = language === "es-419";
    const table = page.getByTestId("transacciones-records");
    const rows = table.locator("tbody tr");
    const missing = rows.nth(0).locator("[data-record-workflow]");
    const ready = rows.nth(1).locator("[data-record-workflow]");
    await expect(missing).toHaveText(spanish ? "Faltan datos" : "Missing data");
    await expect(ready).toHaveText(spanish ? "Listo" : "Ready");
    await expect(rows.nth(1).locator('[data-col="missing"]')).toHaveText("");
    const reason = rows.nth(0).locator("[data-record-missing]");
    await expect(reason).toHaveText(spanish ? "Falta el tipo de gasto+2" : "Expense type is missing+2");
    await reason.hover();
    await expect(page.getByRole("tooltip")).toHaveText(spanish ? "Falta el tipo de gasto · Falta la forma de pago · Falta el RNC" : "Expense type is missing · Payment method is missing · RNC is missing");
    await page.mouse.move(0, 0);
    for (const [density, label, height] of [["compacto", spanish ? "Compacto" : "Compact", 40], ["normal", "Normal", 48], ["amplio", spanish ? "Amplio" : "Roomy", 56]] as const) {
      await page.getByRole("button", { name: spanish ? "Opciones de vista" : "View options", exact: true }).click();
      await page.getByRole("radio", { name: spanish ? "Altura de filas" : "Row height", exact: true }).check();
      await page.getByRole("radio", { name: label, exact: true }).check();
      await page.keyboard.press("Escape");
      await expect(table).toHaveAttribute("data-density", density);
      const geometry = await rows.evaluateAll((elements) => elements.map((row) => ({ height: row.getBoundingClientRect().height, chips: Array.from(row.querySelectorAll("[data-record-workflow]")).map((chip) => ({ width: chip.getBoundingClientRect().width, height: chip.getBoundingClientRect().height, lineHeight: Number.parseFloat(getComputedStyle(chip).lineHeight), whiteSpace: getComputedStyle(chip).whiteSpace })) })));
      for (const row of geometry) {
        expect(row.height).toBe(height);
        for (const chip of row.chips) {
          expect(chip.width).toBe(120);
          expect(chip.height).toBeLessThan(height);
          expect(chip.whiteSpace).toBe("nowrap");
          expect(chip.height).toBeLessThan(chip.lineHeight * 2);
        }
      }
    }
    const card = page.locator('[data-overview-card="fiscal"]');
    await expect(card).toContainText("17");
    await expect(card).toContainText(spanish ? "Complétalos antes de declarar" : "Complete them before filing");
    await card.click();
    await expect(card).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => fixture.calls.filter((call) => call.path.endsWith("/reports/query")).some((call) => (call.body as { filters?: { ready?: boolean } }).filters?.ready === false)).toBe(true);
    await expect(table.locator('[data-record-workflow="ready"]')).toHaveCount(0);
    await expect(rows).toHaveCount(2);
  });
}

for (const width of [1440, 390]) {
  for (const theme of ["light", "dark"] as const) {
    test(`readiness Registros ${width}px ${theme} es-419`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await openReadinessRecords(page, "es-419", theme);
      const records = page.getByTestId("transacciones-records");
      await expect(records.locator('[data-record-workflow="not_ready"]').first()).toHaveText("Faltan datos");
      await expect(records.locator('[data-record-workflow="ready"]').first()).toHaveText("Listo");
      if (width === 390) {
        await expect(records.locator("[data-record-missing]")).toHaveCount(0);
        await expect(records).not.toContainText("Falta el tipo de gasto");
        await expect(records).not.toContainText("+2");
      }
      await page.getByRole("button", { name: "Ocultar guía", exact: true }).click();
      await records.locator("[data-record-workflow]").first().scrollIntoViewIfNeeded();
      const screenshot = testInfo.outputPath(`receipt-upload-registros-${width}-${theme}-es-419.png`);
      await page.screenshot({ path: screenshot, fullPage: true, animations: "disabled" });
      await testInfo.attach(`Registros ${width}px ${theme} es-419`, { path: screenshot, contentType: "image/png" });
      if (process.env.EVIDENCE_DIR) {
        await mkdir(process.env.EVIDENCE_DIR, { recursive: true });
        await page.screenshot({ path: join(process.env.EVIDENCE_DIR, `registros-${width}-${theme}-es-419.png`), fullPage: true, animations: "disabled" });
      }
    });
  }
}


test("readiness opened expense shows the complete missing list", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openReadinessRecords(page, "es-419", "light", true);
  await page.getByTestId("transacciones-records").locator("tbody tr").first().click();
  const detail = page.getByTestId("business-expense-detail");
  await expect(detail).toBeVisible();
  await expect(page.locator("[data-record-missing-list] li")).toHaveText([
    "Falta el tipo de gasto",
    "Falta la forma de pago",
    "Falta el RNC",
  ]);
});
