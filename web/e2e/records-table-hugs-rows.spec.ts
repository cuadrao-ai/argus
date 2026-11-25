import { expect, test, type Page } from "@playwright/test";
import { copyFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { createBusinessReportHttpFixture, fixtureId } from "../__tests__/fixtures/business-report-http-fixture";
import { dossierFixtureIds } from "../components/business-app/dossier-fixtures";
import { installReceiptBusiness } from "./support/business-receipt-fixture";

// A list is as tall as its rows, its footer sits under the last row, and the footer shows only controls that change something.

const CURRENT_NOTE = "Revisar la referencia de la orden antes de archivar el comprobante de esta compra.";

type RecordOptions = {
  hold?: Promise<void>;
  dossier?: boolean;
  files?: number[];
  readOnly?: boolean;
  theme?: "light" | "dark";
};

async function openRegistros(page: Page, count: number, { hold, dossier = false, files, readOnly = false, theme }: RecordOptions = {}) {
  const reports = createBusinessReportHttpFixture();
  const purchases = reports.records.filter((row) => row.family === "purchase" && row.report_date === "2026-10-20").slice(0, count);
  expect(purchases).toHaveLength(count);
  if (files) {
    const original = reports.records[0].attachment_sources![0];
    reports.controls.readOnly = readOnly;
    purchases.forEach((row, index) => {
      // Supporting files can exist without an original, and the document flag cannot supply a count.
      row.has_document = files[index] !== 2;
      row.note = index === 0 ? CURRENT_NOTE : null;
      row.attachment_sources = Array.from({ length: files[index] }, (_, file) => ({
        ...original,
        source_id: fixtureId(500 + index * 10 + file),
        receipt_id: fixtureId(700 + index * 10 + file),
        filename: `Archivo ${file + 1}.pdf`,
      }));
    });
    reports.controls.presentation = {
      ...reports.controls.presentation,
      hidden: reports.controls.presentation.order.filter(key => !["counterparty", "date", "gross_amount", "note", "attachment"].includes(key)),
    };
  }
  reports.records.splice(0, reports.records.length, ...purchases);
  if (dossier) {
    const selected = purchases[0];
    selected.draft_id = dossierFixtureIds.ready;
    selected.row_id = `draft:${selected.draft_id}`;
    selected.note = CURRENT_NOTE;
    reports.controls.presentation = {
      ...reports.controls.presentation,
      hidden: reports.controls.presentation.hidden.filter((column) => column !== "note" && column !== "attachment"),
    };
  }
  await page.clock.setFixedTime(new Date("2026-10-20T15:00:00Z"));
  const source = await installReceiptBusiness(page, (parts, route, fixture) => {
    if (dossier && parts.join("/") === `drafts/${dossierFixtureIds.ready}/dossier`) {
      return fixture.dossier(dossierFixtureIds.ready).then((record) => ({
        ...record, space_id: "fixture-space", current_note: CURRENT_NOTE, note_edit_available: true, supporting_append_available: true,
      }));
    }
    if (parts[0] !== "reports" && parts[0] !== "report-views") return undefined;
    const request = route.request();
    return Promise.resolve(parts[0] === "reports" ? hold : undefined)
      .then(() => reports.request(request.url(), { method: request.method(), headers: request.headers(), body: request.postData() ?? undefined }))
      .then(async (response) => route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) }))
      .then(() => null);
  }, theme);
  if (dossier) await source.approveDraft(dossierFixtureIds.ready, 2, "registros-details", "record_expense");
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

  for (const [column, heading] of [["note", "Nota"], ["attachment", "Archivos de respaldo"]] as const) {
    test(`Registros opens Detalles at the ${column} card`, async ({ page }) => {
      await openRegistros(page, 1, { dossier: true, files: [2] });
      const entry = page.locator(`button[data-record-${column}]`);
      if (column === "attachment") {
        await expect(entry).toHaveText(width === 1440 ? "2" : "");
        await expect(entry).toHaveAccessibleName(/2 archivos/);
      }
      await entry.click();
      const details = page.getByRole("tabpanel", { name: "Detalles", exact: true });
      await expect(page.getByRole("tab", { name: "Detalles", exact: true })).toHaveAttribute("aria-selected", "true");
      await expect(details.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      if (column === "note") {
        // The text box's own focus edge is the one highlight.
        const note = details.getByRole("textbox", { name: "Nota", exact: true });
        await expect(note).toBeFocused();
        await expect(note).toHaveValue(CURRENT_NOTE);
        await expect(details.locator("[data-landing]")).toHaveCount(0);
      } else {
        // The files card marks its own edge, with no second box inside it.
        await expect(details.locator('[data-testid="dossier-supporting"][data-landing]')).toBeVisible();
        await expect(details.locator('[data-testid="dossier-supporting"] [data-landing]')).toHaveCount(0);
        await expect(details.getByRole("button", { name: "Agregar archivo", exact: true })).toBeFocused();
      }
    });
  }

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

test("Registros protects an unsaved Nota on close, reload, and another row", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await openRegistros(page, 2, { dossier: true });
  const noteEntry = page.locator("button[data-record-note]").filter({ hasText: CURRENT_NOTE });
  const editedRow = page.getByRole("row").filter({ has: noteEntry });
  const otherRow = page.getByRole("grid", { name: "Registros" }).getByRole("rowgroup").nth(1)
    .getByRole("row").filter({ hasNot: noteEntry });
  await expect(editedRow).toHaveCount(1);
  await noteEntry.click();
  const drawer = page.getByTestId("side-drawer");
  const note = drawer.getByRole("textbox", { name: "Nota", exact: true });
  const close = drawer.getByRole("button", { name: "Cerrar", exact: true });
  const changed = "Verificar el recibo.";
  await note.fill(changed);
  await close.click();
  const warning = page.getByRole("alertdialog", { name: "¿Descartar los cambios?" });
  await expect(warning).toBeVisible();
  await warning.getByRole("button", { name: "Seguir editando" }).click();
  await expect(note).toHaveValue(changed);
  const reloadWarning = page.waitForEvent("dialog").then(async dialog => {
    const type = dialog.type();
    await dialog.dismiss();
    return type;
  });
  await page.evaluate(() => { window.location.reload(); });
  expect(await reloadWarning).toBe("beforeunload");
  await expect(note).toHaveValue(changed);
  await otherRow.click({ position: { x: 40, y: 20 } });
  await expect(warning).toBeVisible();
  await warning.getByRole("button", { name: "Seguir editando" }).click();
  await expect(note).toHaveValue(changed);
  await close.click();
  await warning.getByRole("button", { name: "Descartar cambios" }).click();
  await expect(drawer).toHaveCount(0);
});

test("the Registros skeleton holds its height while the first page loads", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  let release = () => {};
  await openRegistros(page, 1, { hold: new Promise<void>((resolve) => { release = resolve; }) });
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

for (const theme of ["light", "dark"] as const) {
  test(`Adjunto shows the reported files and names the Detalles card in ${theme}`, async ({ page }, testInfo) => {
    const counts = [1, 2, 3, 4];
    await page.setViewportSize({ width: 1440, height: 900 });
    await openRegistros(page, counts.length, { files: counts, theme, readOnly: true });
    const buttons = page.locator('td[data-col="attachment"] button');
    await expect(buttons).toHaveText(counts.map(String));
    for (const [index, count] of counts.entries()) {
      await expect(buttons.nth(index)).toHaveAccessibleName(new RegExp(`\\b${count} archivo`));
    }
    await page.getByRole("button", { name: "Ocultar guía", exact: true }).click();
    await buttons.nth(2).hover();
    await expect(page.getByRole("tooltip")).toHaveText(/Detalles.*Archivos de respaldo/);
    const filename = `receipt-upload-registros-adjunto-${theme}.png`;
    const path = testInfo.outputPath(filename);
    await page.screenshot({ path, animations: "disabled" });
    await testInfo.attach(filename, { path, contentType: "image/png" });
    if (process.env.EVIDENCE_DIR) {
      await mkdir(process.env.EVIDENCE_DIR, { recursive: true });
      await copyFile(path, join(process.env.EVIDENCE_DIR, filename));
    }
  });
}

for (const readOnly of [true, false]) {
  test(`Registros shows notes and empty file cells for a reader who ${readOnly ? "cannot" : "can"} append`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openRegistros(page, 2, { files: [0, 0], readOnly });
    const rows = page.locator("tr[data-record-key]");
    const note = rows.first().locator('[data-col="note"] button');
    await expect(note).toHaveText(CURRENT_NOTE);
    expect(await note.evaluate(el => el.scrollWidth > el.clientWidth && getComputedStyle(el).textOverflow === "ellipsis")).toBe(true);
    await note.hover();
    await expect(page.getByRole("tooltip")).toHaveText(CURRENT_NOTE);
    const empty = rows.nth(1);
    for (const [column, label] of [["attachment", "Agregar adjunto"], ["note", "Agregar nota"]]) {
      await page.mouse.move(0, 0);
      const cell = empty.locator(`[data-col="${column}"]`);
      const dash = cell.getByText("-", { exact: true });
      await expect(dash).toBeVisible();
      if (readOnly) {
        await expect(cell.getByRole("button")).toHaveCount(0);
      } else {
        await expect(cell.locator("svg")).toBeHidden();
        await cell.getByRole("button").hover();
        await expect(dash).toBeHidden();
        await expect(cell.locator("svg")).toBeVisible();
        await expect(page.getByRole("tooltip")).toHaveText(label);
      }
    }
  });
}
