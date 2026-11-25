import assert from "node:assert/strict";
import { afterAll, afterEach, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { reportRequestSchema, type ReportRecord } from "@/lib/business-reports-api";
import { mountConnectedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeEach(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); (await import("@/components/business-app/foundation/toasts")).clearToasts(); await GlobalRegistrator.unregister(); });
afterAll(() => { if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

type Mode = "table" | "dgii";
type Options = NonNullable<Parameters<typeof mount>[0]>;
const SENTENCES = {
  "es-419": { 1: "1 comprobante de este período sigue en la Bandeja.", 12: "12 comprobantes de este período siguen en la Bandeja.", open: "Ver en Bandeja" },
  en: { 1: "1 document from this period is still in the Inbox.", 12: "12 documents from this period are still in the Inbox.", open: "View in Inbox" },
} as const;
const panel = () => document.querySelector<HTMLElement>('[data-testid="records-export-panel"]');
const downloadButton = () => document.querySelector<HTMLButtonElement>('[data-testid="records-export-download"]');
const card = (mode: Mode) => document.querySelector<HTMLElement>(`[data-testid="records-export-mode-${mode}"]`)!;
const notices = () => document.querySelector<HTMLElement>('[data-testid="records-export-notices"]');
const bandeja = () => document.querySelector<HTMLElement>('[data-testid="records-export-bandeja-notice"]');
const action = (notice: Element | null) => notice?.querySelector<HTMLElement>('[data-testid="records-export-notice-action"]') ?? null;

/** Purchases with every 606 notice: complete lines, three pending fiscal data, and two in other currencies. */
function fiscalBooks(rows: ReportRecord[]) {
  const purchases = rows.filter((row) => row.family === "purchase");
  purchases.slice(0, 4).forEach((row) => { row.stage = "ready_for_export"; row.fiscal_data = "complete"; row.ready = true; row.missing = []; });
  purchases.slice(4, 9).forEach((row, index) => { row.stage = "needs_fiscal_data"; row.fiscal_data = "missing"; row.ready = false; row.currency = index < 3 ? "DOP" : "USD"; });
}

/** Every purchase is a complete pesos line, so the 606 has rows and no notice of its own. */
const cleanBooks = (rows: ReportRecord[]) => rows.filter((row) => row.family === "purchase").forEach((row) => { row.stage = "ready_for_export"; row.fiscal_data = "complete"; row.ready = true; row.missing = []; row.currency = "DOP"; });

async function openIn(mode: Mode, count: number, options: Options = {}) {
  const page = await mount(options);
  page.fixture.controls.bandejaCount = count;
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => downloadButton() !== null && !downloadButton()!.disabled);
  if (mode === "dgii") await page.click(card("dgii").querySelector("input"));
  return page;
}

for (const mode of ["table", "dgii"] as const) {
  test(`with nothing in the Bandeja the ${mode} export says nothing about it`, async () => {
    await openIn(mode, 0, { edit: cleanBooks });
    assert.equal(bandeja(), null);
    assert.equal(notices(), null, "no other notice here, so no list");
    assert.doesNotMatch(panel()!.textContent!, /Bandeja/);
  });

  for (const language of ["es-419", "en"] as const) {
    for (const count of [1, 12] as const) {
      test(`the ${mode} export says ${count} still in the Bandeja in ${language}`, async () => {
        await openIn(mode, count, { language, edit: cleanBooks });
        const line = bandeja()!;
        assert.equal(line.querySelector("p")!.textContent, SENTENCES[language][count]);
        assert.ok(card(mode).contains(line), "the line sits inside the chosen option");
        assert.equal(notices()!.children.length, 1, "alone, it is the whole list");
        assert.ok(line.querySelector(".lucide-circle-minus"));
        assert.equal(action(line)!.textContent, SENTENCES[language].open);
        assert.equal(downloadButton()!.disabled, false, "the notice never blocks the export");
      });
    }
  }
}

test("the line moves with the chosen option and is always last, after the three 606 notices", async () => {
  const page = await openIn("table", 3, { edit: fiscalBooks });
  page.fixture.controls.rncSuppliers = [{ name: "Suplidor registrado", rnc: "101001577", estado: "SUSPENDIDO", status: "rnc_inactive", record_count: 2 }];
  assert.ok(card("table").contains(bandeja()));
  await page.click(downloadButton()!.closest('[role="dialog"]')!.querySelector('[aria-label="Cerrar"]'));
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => downloadButton() !== null && !downloadButton()!.disabled);
  await page.click(card("dgii").querySelector("input"));
  assert.equal(card("table").contains(bandeja()), false);
  const list = notices()!;
  assert.ok(card("dgii").contains(list));
  assert.deepEqual([...list.children].map((item) => item.querySelector("p")!.textContent), [
    "1 proveedor con RNC no activo o sin verificar",
    "3 compras tienen datos fiscales pendientes y no se incluyen.",
    "2 compras en USD necesitan tasa y no se incluyen.",
    "3 comprobantes de este período siguen en la Bandeja.",
  ]);
  assert.equal(list.lastElementChild, bandeja());
  assert.deepEqual([...list.children].map((item) => action(item)?.textContent ?? null), ["Ver proveedores", "Revisar", null, "Ver en Bandeja"], "each action has its own column; the rate notice has none");
  for (const item of list.children) {
    const column = action(item);
    if (!column) continue;
    assert.equal(column.parentElement, item, "the action is a column of the notice, not part of its sentence");
    assert.equal(column.previousElementSibling!.contains(column), false);
    for (const name of ["min-w-[112px]", "ml-4", "shrink-0", "text-right"]) assert.ok(column.classList.contains(name), name);
  }
  assert.ok(list.classList.contains("gap-[10px]"));
});

test("Ver en Bandeja closes the dialog and opens the Bandeja", async () => {
  const page = await openIn("dgii", 3);
  await page.click(page.button("Ver en Bandeja"));
  assert.equal(panel(), null);
  assert.deepEqual(page.opened, [{ kind: "inbox" }]);
});

test("a person who cannot prepare sees the count with no link", async () => {
  const page = await mount();
  page.fixture.controls.bandejaCount = 3;
  page.context.chosen.capabilities = ["read"];
  await page.rerender();
  await page.click(document.querySelector('[data-testid="records-export"]'));
  await page.settle(() => downloadButton() !== null && !downloadButton()!.disabled);
  assert.equal(bandeja()!.querySelector("p")!.textContent, SENTENCES["es-419"][12].replace("12", "3"));
  assert.equal(action(bandeja()), null);
  assert.equal(page.button("Ver en Bandeja"), undefined);
});

test("the sales export shows the same line inside the chosen option", async () => {
  const initial = reportRequestSchema.parse({ schema_version: 2, filters: { record_families: ["sale"], currencies: ["DOP"] } });
  const page = await openIn("table", 2, { initial });
  assert.ok(card("table").contains(bandeja()));
  assert.equal(document.querySelector('[data-testid="records-export-mode-dgii"]'), null);
  assert.equal(notices()!.children.length, 1);
  assert.ok(page.button("Ver en Bandeja"));
});
