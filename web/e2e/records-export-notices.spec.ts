import { expect, test, type Locator, type Page } from "@playwright/test";
import { createBusinessReportHttpFixture } from "../__tests__/fixtures/business-report-http-fixture";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";
import { fulfillSyntheticBusinessFallback } from "./support/synthetic-business-fallback";

async function open606(page: Page) {
  const fixture = createBusinessReportHttpFixture();
  const purchases = fixture.records.filter((row) => row.family === "purchase");
  purchases.forEach((row) => { row.currency = "DOP"; row.fiscal_data = "complete"; row.stage = "ready_for_export"; });
  purchases[0].fiscal_data = "missing";
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
    await expect(first.locator(":scope > div > span").last()).toHaveText("Suspendido");
    await expect(list.locator(":scope > li").nth(1).locator(":scope > div > span").last()).toHaveText("No encontrado");
    await expect(first.locator(":scope > span")).toHaveText(fixture.controls.rncSuppliers[0].rnc);
    const supplier = await first.evaluate((element) => {
      const line = element.firstElementChild!;
      const name = line.firstElementChild!.getBoundingClientRect();
      const status = line.lastElementChild!.getBoundingClientRect();
      const rnc = element.lastElementChild!;
      return { nameTop: name.top, statusTop: status.top, statusRight: status.right, lineRight: line.getBoundingClientRect().right, rncTop: rnc.getBoundingClientRect().top, nameBottom: name.bottom, font: getComputedStyle(rnc).fontFamily, statusColor: getComputedStyle(line.lastElementChild!).color, nameColor: getComputedStyle(line.firstElementChild!).color };
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
