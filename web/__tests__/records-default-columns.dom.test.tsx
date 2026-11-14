import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { RecordRow } from "@/components/business-app/transacciones/transacciones-model";
import { sampleRecordsColumns, sampleRecordsPreferences } from "@/components/business-app/transacciones/sample-records-preferences";
import { moveRecordsColumn, recordsColumnSettings, taxpayerIdText, toggleRecordsColumn, visibleRecordsColumns, type RecordsViewPreferences } from "@/components/business-app/transacciones/records-view-preferences";

const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
beforeAll(() => {
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); cleanup = async () => {}; document.body.innerHTML = ""; });

const shownKeys = (value: RecordsViewPreferences) => visibleRecordsColumns(value).map(({ key }) => key);
const forFamily = (family: "purchase" | "sale"): RecordsViewPreferences => ({ ...sampleRecordsPreferences(), columns: sampleRecordsColumns(family) });

test("the server's default table starts with RNC o Cédula on Compras and on Ventas", () => {
  assert.deepEqual(shownKeys(forFamily("purchase")), ["counterparty_id", "date", "expense_type", "net_amount", "itbis_amount", "gross_amount", "stage"]);
  assert.deepEqual(shownKeys(forFamily("sale")), ["counterparty_id", "date", "net_amount", "itbis_amount", "gross_amount", "stage"]);
  assert.deepEqual(recordsColumnSettings(forFamily("purchase")).filter((column) => !column.shown).map(({ key }) => key), ["counterparty", "fiscal_number", "note", "attachment", "payment_form", "funding"]);
});

test("the person can hide any column, but the last one shown stays", () => {
  let value = forFamily("purchase");
  const shown = shownKeys(value);
  for (const key of shown.slice(0, -1)) {
    value = toggleRecordsColumn(value, key);
    assert.equal(shownKeys(value).includes(key), false, `${key} hides`);
  }
  assert.deepEqual(shownKeys(value), shown.slice(-1));
  assert.equal(toggleRecordsColumn(value, shown.at(-1)!), value);
  assert.deepEqual(shownKeys(toggleRecordsColumn(value, "note")), ["stage", "note"]);
});

test("any column moves, to the first place too, and the first shown column is the frozen one", () => {
  const initial = forFamily("purchase");
  assert.deepEqual(visibleRecordsColumns(initial).filter((column) => column.pin).map(({ key, pin }) => [key, pin]), [["counterparty_id", "left"]]);
  const moved = moveRecordsColumn(initial, "date", 0);
  assert.equal(moved.order[0], "date");
  assert.deepEqual(visibleRecordsColumns(moved).filter((column) => column.pin).map(({ key, pin }) => [key, pin]), [["date", "left"]]);
  const hidden = toggleRecordsColumn(moved, "date");
  assert.deepEqual(visibleRecordsColumns(hidden).filter((column) => column.pin).map(({ key, pin }) => [key, pin]), [["counterparty_id", "left"]]);
  const proofLast = moveRecordsColumn(toggleRecordsColumn(initial, "attachment"), "attachment", initial.order.length);
  assert.deepEqual(visibleRecordsColumns(proofLast).filter((column) => column.pin).map(({ key, pin }) => [key, pin]), [["counterparty_id", "left"], ["attachment", "right"]]);
});

test("a taxpayer id reads with the DGII's hyphens", () => {
  assert.equal(taxpayerIdText("101001577"), "1-01-00157-7");
  assert.equal(taxpayerIdText("00100000001"), "001-0000000-1");
  assert.equal(taxpayerIdText("12345"), "12345");
});

const row = (id: string, name: string | null, taxpayer: string | null): RecordRow => ({
  id, kind: "gasto", occurredOn: "2026-10-25", counterparty: name, money: { amount: "-1250000.00", currency: "DOP" }, categoryId: null, account: null, hasProof: false,
  marks: { personal: false, markedBy: null, fiscal: null }, opens: { kind: "expense", expenseId: id },
  report: { family: "purchase", stage: "ready_for_export", currency: "DOP", gross_amount: "1250000.00", net_amount: "1059322.03", itbis_amount: "190677.97", counterparty: name, counterparty_key: taxpayer, fiscal_number: null, dgii_606: null, workflow_blockers: [] } as unknown as RecordRow["report"],
});

async function mount(preferences: RecordsViewPreferences) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { RecordsAnnotationsPreview } = await import("@/components/business-app/transacciones/RecordsAnnotationsPreview");
  const { RecordsTable } = await import("@/components/business-app/transacciones/TransaccionesRecords");
  const value = { chosen: { space_id: "fixture-space", capabilities: ["read"] }, records: { workspace: { receipt_limits: { max_bytes: 100, media_types: ["application/pdf"] } } }, panel: { kind: "transactions" }, openPanel: () => {} } as unknown as BusinessContextValue;
  const records = [row("known", "Ferretería Ozama", "101001577"), row("person", "Ana Pérez", "00100000001"), row("none", "Colmado Sin RNC", null)];
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><RecordsAnnotationsPreview><RecordsTable records={records} preferences={preferences} density="normal" rowRef={() => {}} /></RecordsAnnotationsPreview></BusinessContext.Provider></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  return { act, host };
}
const cell = (host: HTMLElement, id: string, column: string) => host.querySelector<HTMLElement>(`tr[data-record-id="${id}"] td[data-col="${column}"]`)!;

test("every column title is bold in one style, and the table names the new column", async () => {
  const { host } = await mount(forFamily("purchase"));
  const titles = [...host.querySelectorAll<HTMLElement>("thead th")];
  assert.equal(titles[0].textContent, "RNC o Cédula");
  assert.equal(titles.length, 7);
  for (const title of titles) {
    assert.match(title.className, /\bfont-semibold\b/, title.textContent ?? "");
    assert.doesNotMatch(title.className, /\bfont-normal\b/);
  }
  assert.equal(new Set(titles.map((title) => title.className.match(/\btext-\[#[0-9a-fA-F]+\]/)?.[0])).size, 1);
});

test("the RNC cell shows hyphens in tabular figures, a dash with none, and the name on hover", async () => {
  const { host, act } = await mount(forFamily("purchase"));
  const known = cell(host, "known", "counterparty_id");
  assert.match(known.className, /\bfont-mono\b/); assert.match(known.className, /\btabular-nums\b/); assert.match(known.className, /\btext-left\b/);
  const digits = known.querySelector<HTMLElement>("[data-taxpayer-id]")!;
  assert.equal(digits.firstChild?.textContent, "1-01-00157-7");
  assert.equal(known.textContent, "1-01-00157-7, Ferretería Ozama");
  assert.equal(cell(host, "person", "counterparty_id").querySelector("[data-taxpayer-id]")?.firstChild?.textContent, "001-0000000-1");
  assert.equal(cell(host, "none", "counterparty_id").querySelector("[data-taxpayer-id]"), null);
  assert.match(cell(host, "none", "counterparty_id").textContent ?? "", /^-/);
  const { TOOLTIP_DELAY_MS } = await import("@/components/ui/Tooltip");
  await act(async () => { digits.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); await new Promise((resolve) => setTimeout(resolve, TOOLTIP_DELAY_MS + 30)); });
  const tip = document.querySelector('[role="tooltip"]');
  assert.equal(tip?.textContent, "Ferretería Ozama");
  assert.equal(digits.getAttribute("aria-describedby"), tip?.id);
});

test("the frozen cells follow the first column: the date freezes once it leads", async () => {
  const first = await mount(forFamily("purchase"));
  assert.equal(cell(first.host, "known", "counterparty_id").dataset.pinned, "left");
  assert.equal(cell(first.host, "known", "date").dataset.pinned, undefined);
  await cleanup(); document.body.innerHTML = "";
  const moved = await mount(moveRecordsColumn(forFamily("purchase"), "date", 0));
  assert.equal(cell(moved.host, "known", "date").dataset.pinned, "left");
  assert.match(cell(moved.host, "known", "date").className, /\bsticky\b/);
  assert.equal(cell(moved.host, "known", "counterparty_id").dataset.pinned, undefined);
  assert.equal(moved.host.querySelector<HTMLElement>('thead th[data-col="date"]')?.dataset.pinned, "top left");
});
