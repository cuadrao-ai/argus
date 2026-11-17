import { expect, test, type Page } from "@playwright/test";
import { createBusinessReportHttpFixture } from "../__tests__/fixtures/business-report-http-fixture";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

// A list is as tall as its rows, its footer sits under the last row, and the footer shows only controls that change something.

async function openRegistros(page: Page, count: number, hold?: Promise<void>) {
  const reports = createBusinessReportHttpFixture();
  const purchases = reports.records.filter((row) => row.family === "purchase" && row.report_date === "2026-10-20").slice(0, count);
  expect(purchases).toHaveLength(count);
  reports.records.splice(0, reports.records.length, ...purchases);
  await page.clock.setFixedTime(new Date("2026-10-20T15:00:00Z"));
  await installReceiptBusiness(page, (parts, route) => {
    if (parts[0] !== "reports" && parts[0] !== "report-views") return undefined;
    const request = route.request();
    return Promise.resolve(parts[0] === "reports" ? hold : undefined)
      .then(() => reports.request(request.url(), { method: request.method(), headers: request.headers(), body: request.postData() ?? undefined }))
      .then(async (response) => route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) }))
      .then(() => null);
  });
  await page.goto("/biz?view=transactions");
}

/** What the footer shows, and how much room the list leaves between its last row and the footer. */
function footer(page: Page) {
  return page.getByTestId("records-pagination").evaluate((node) => {
    const frame = document.querySelector<HTMLElement>('[data-testid="transacciones-scroll"]');
    const rows = document.querySelector<HTMLElement>('[data-testid="transacciones-records"]')!;
    const bottom = (frame ?? rows).getBoundingClientRect().bottom;
    return {
      count: node.querySelector('[data-testid="records-count"]')?.textContent ?? null,
      picker: Boolean(node.querySelector('button[aria-haspopup="dialog"]')),
      arrows: Boolean(node.querySelector("nav")),
      emptyBelowRows: frame ? Math.max(0, Math.round(frame.clientHeight - rows.getBoundingClientRect().height)) : 0,
      gap: Math.round(node.getBoundingClientRect().top - bottom),
    };
  });
}

for (const width of [1440, 390]) test.describe(`at ${width}px`, () => {
  test.beforeEach(async ({ page }) => { await page.setViewportSize({ width, height: 1000 }); });

  for (const { count, label, picker, arrows } of [
    { count: 1, label: "1–1 de 1 registro", picker: false, arrows: false },
    { count: 25, label: "1–25 de 25 registros", picker: false, arrows: false },
    { count: 60, label: "1–25 de 60 registros", picker: true, arrows: true },
  ]) test(`Registros with ${count} records`, async ({ page }) => {
    await openRegistros(page, count);
    await expect(page.getByTestId("records-count")).toHaveText(label);
    expect(await footer(page)).toEqual({ count: label, picker, arrows, emptyBelowRows: 0, gap: 0 });
  });

  test("Registros with 40 records at 50 per page", async ({ page }) => {
    await openRegistros(page, 40);
    await page.getByTestId("records-pagination").getByRole("button", { name: /por página/ }).click();
    await page.getByRole("button", { name: "50 por página" }).click();
    await expect(page.getByTestId("records-count")).toHaveText("1–40 de 40 registros");
    expect(await footer(page)).toEqual({ count: "1–40 de 40 registros", picker: true, arrows: false, emptyBelowRows: 0, gap: 0 });
  });
});

test("the Registros skeleton holds its height while the first page loads", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  let release = () => {};
  await openRegistros(page, 1, new Promise<void>((resolve) => { release = resolve; }));
  const skeleton = page.getByTestId("transacciones-loading").locator("table").first();
  await expect(skeleton).toBeAttached();
  expect((await skeleton.boundingBox())!.height).toBeGreaterThanOrEqual(44 + 8 * 40);
  release();
  await expect(page.getByTestId("records-count")).toHaveText("1–1 de 1 registro");
});

test("Bandeja's footer follows the same rule", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await installReceiptBusiness(page);
  await page.goto("/biz?view=inbox");
  await expect(page.getByTestId("records-count")).toHaveText(/de \d+ elementos?$/);
  const shown = await page.getByTestId("records-pagination").evaluate((node) => ({ picker: Boolean(node.querySelector('button[aria-haspopup="dialog"]')), arrows: Boolean(node.querySelector("nav")) }));
  expect(shown).toEqual({ picker: false, arrows: false });
});
