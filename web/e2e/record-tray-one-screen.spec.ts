import { expect, test, type Page } from "@playwright/test";
import { createBusinessReportHttpFixture } from "../__tests__/fixtures/business-report-http-fixture";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { bandejaRows, installReceiptBusiness, reviewAction } from "./support/business-receipt-fixture";

// One screen sits under an open record: the list it belongs to, named once in the top bar. Opening or closing a
// record moves neither the bar title nor the list, and a record opened from a link never mounts another list first.

const APPROVED = { id: "rcpt-confirmed", merchant: "Nube Hosting" };

async function installBusiness(page: Page) {
  const reports = createBusinessReportHttpFixture();
  await page.addInitScript(() => {
    const mounts: string[] = [];
    const seen = new WeakSet<Element>();
    (window as unknown as { __mounts: string[] }).__mounts = mounts;
    new MutationObserver(() => {
      for (const id of ["reception-preview", "transacciones"]) {
        const node = document.querySelector(`[data-testid="${id}"]`);
        if (node && !seen.has(node)) { seen.add(node); mounts.push(id); }
      }
    }).observe(document, { subtree: true, childList: true });
  });
  await installReceiptBusiness(page, (parts, route, source) => {
    if (parts[0] === "reports" || parts[0] === "report-views") {
      const request = route.request();
      return reports.request(request.url(), { method: request.method(), headers: request.headers(), body: request.postData() ?? undefined })
        .then(async (response) => route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) }))
        .then(() => null);
    }
    if (parts[0] === "drafts" && parts[2] === "dossier") {
      const row = reports.records.find((record) => record.draft_id === parts[1]);
      if (!row) return undefined;
      return source.dossier(dossierFixtureIds.ready).then((dossier) => ({ ...dossier, draft_id: row.draft_id, facts: { ...dossier.facts, counterparty: { ...dossier.facts.counterparty, value: row.counterparty } } }));
    }
    if (parts[0] === "activity") return Promise.resolve({ items: [{ id: "activity-1", occurred_at: "2026-10-20T15:00:00Z", actor: null, action: "approve_expense", object: { kind: "receipt", id: APPROVED.id, label: APPROVED.merchant } }], next_cursor: null });
    return undefined;
  });
}

/** Where the bar title and the list's first control sit, and every Agregar a person can reach. */
function layout(page: Page) {
  return page.evaluate(() => {
    const title = document.querySelector('[data-testid="business-desktop-header"] h1');
    const list = document.querySelector('[data-testid="workspace-canvas"] [role="tablist"]');
    const agregar = [...document.querySelectorAll("button")].filter((node) => node.textContent?.includes("Agregar") && node.getBoundingClientRect().width > 0 && !node.closest("[inert]"));
    return { title: title?.textContent ?? null, titleTop: title ? Math.round(title.getBoundingClientRect().top) : null, listTop: list ? Math.round(list.getBoundingClientRect().top) : null, agregar: agregar.length };
  });
}

const recordTitle = (page: Page) => page.getByTestId("side-drawer").locator("#receipt-review-title");
const registrosRow = (page: Page, index: number) => page.getByRole("grid", { name: "Registros" }).getByRole("rowgroup").nth(1).getByRole("row").nth(index);

/** Opens a Registros row and answers the record's title, then closes it. */
async function titleOf(page: Page, index: number) {
  await registrosRow(page, index).click();
  await expect(recordTitle(page)).toHaveText(/^Proveedor /);
  const title = await recordTitle(page).textContent();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("side-drawer")).toHaveCount(0);
  return title!;
}

test.describe("one screen under an open record at 1440px", () => {
  test.beforeEach(async ({ page }) => {
    // Tall enough that the rows sit in view unscrolled, so a click never scrolls the list before it is measured.
    await page.setViewportSize({ width: 1440, height: 1600 });
    await installBusiness(page);
  });

  test("Registros: the bar title and the list hold still, and one Agregar stays", async ({ page }) => {
    await page.goto("/biz?view=transactions");
    await expect(registrosRow(page, 1)).toBeVisible();
    const closed = await layout(page);
    expect(closed).toMatchObject({ title: "Registros", agregar: 1 });
    await registrosRow(page, 1).click();
    await expect(recordTitle(page)).toHaveText(/^Proveedor /);
    expect(await layout(page), "a record opened beside Registros").toEqual(closed);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("side-drawer")).toHaveCount(0);
    expect(await layout(page), "Registros after the record closed").toEqual(closed);
  });

  test("Bandeja: the bar title and the list hold still, and one Agregar stays", async ({ page }) => {
    await page.goto("/biz?view=inbox");
    await expect(bandejaRows(page)).toBeVisible();
    const closed = await layout(page);
    expect(closed).toMatchObject({ title: "Bandeja", agregar: 1 });
    await reviewAction(page, /Ferretería La Esquina/).click();
    await expect(recordTitle(page)).toHaveText("Ferretería La Esquina");
    expect(await layout(page), "a record opened over the Bandeja").toEqual(closed);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("side-drawer")).toHaveCount(0);
    expect(await layout(page), "the Bandeja after the record closed").toEqual(closed);
  });

  test("a click on the next Registros row beside an open record opens that row", async ({ page }) => {
    await page.goto("/biz?view=transactions");
    await expect(registrosRow(page, 2)).toBeVisible();
    const first = await titleOf(page, 1);
    const second = await titleOf(page, 2);
    expect(second).not.toEqual(first);
    await page.reload();
    await expect(registrosRow(page, 2)).toBeVisible();
    const next = (await registrosRow(page, 2).boundingBox())!;
    await registrosRow(page, 1).click();
    await expect(recordTitle(page)).toHaveText(first);
    await page.mouse.click(next.x + 40, next.y + next.height / 2);
    await expect(recordTitle(page)).toHaveText(second);
  });

  test("an approved record opened from Actividad mounts Registros once and never the Bandeja", async ({ page }) => {
    await page.goto("/biz?view=activity");
    await page.getByRole("button", { name: /Aceptó un gasto/ }).click();
    await expect(recordTitle(page)).toHaveText(APPROVED.merchant);
    await expect(page).toHaveURL(new RegExp(`receipt=${APPROVED.id}`));
    await expect(page.getByTestId("transacciones")).toBeVisible();
    await expect.poll(() => layout(page)).toMatchObject({ title: "Registros", agregar: 1 });
    expect(await page.evaluate(() => (window as unknown as { __mounts: string[] }).__mounts)).toEqual(["transacciones"]);
  });

  test("an approved record opened from a link mounts Registros once and opens the linked record", async ({ page }) => {
    await page.goto(`/biz?receipt=${APPROVED.id}`);
    await expect(recordTitle(page)).toHaveText(APPROVED.merchant);
    await expect(page.getByTestId("transacciones")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`receipt=${APPROVED.id}`));
    expect(await page.evaluate(() => (window as unknown as { __mounts: string[] }).__mounts)).toEqual(["transacciones"]);
  });
});
