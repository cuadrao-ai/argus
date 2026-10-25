import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { activeFilterGroups, emptyPreviewFilters, validPreviewAmount } from "@/components/business-app/transacciones/records-filter-preview-model";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; });

async function mount(kind: "filters" | "date") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const Filters = (await import("@/components/business-app/transacciones/RecordsFiltersPreview")).default;
  const DatePreview = (await import("@/components/business-app/transacciones/RecordsDatePreview")).default;
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{kind === "filters" ? <Filters options={null} /> : <DatePreview period={{ key: "custom", from: "2026-10-01", to: "2026-10-25" }} />}</I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  const click = (node: Element | null | undefined) => act(async () => { assert.ok(node); (node as HTMLElement).click(); });
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === text);
  const escape = () => act(async () => { document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  return { act, host, click, button, escape };
}

test("filter draft is discarded on Escape, committed by Apply, and removable by group", async () => {
  const page = await mount("filters");
  await page.click(page.button("Filtros"));
  await page.click(document.querySelector('input[type="checkbox"]'));
  await page.escape();
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]'), null);
  await page.click(page.button("Filtros"));
  assert.equal(document.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked, false);
  await page.click(document.querySelector('input[type="checkbox"]'));
  await page.click(page.button("Comprobante"));
  await page.click([...document.querySelectorAll("label")].find((label) => label.textContent === "Sin documento"));
  await page.click(page.button("Aplicar"));
  const chips = document.querySelector('[data-testid="records-preview-filter-chips"]')!;
  assert.match(chips.textContent ?? "", /Por revisar/);
  assert.match(chips.textContent ?? "", /Sin documento/);
  assert.equal(page.host.querySelector('button[aria-haspopup="dialog"]')?.textContent, "Filtros2");
  await page.click(document.querySelector('button[aria-label="Quitar filtro Revisión"]'));
  assert.doesNotMatch(chips.textContent ?? "", /Por revisar/);
  await page.click(page.button("Limpiar filtros"));
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]'), null);
});

test("amount controls wait for a currency and exact validation rejects an inverted range", async () => {
  const page = await mount("filters"); await page.click(page.button("Filtros")); await page.click(page.button("Moneda y monto"));
  assert.ok([...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')].every((input) => input.disabled));
  await page.click(page.button("USD"));
  assert.ok([...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')].every((input) => !input.disabled));
  assert.equal(validPreviewAmount({ currency: "USD", min: "9007199254740993.01", max: "9007199254740993.00" }), false);
  assert.deepEqual(activeFilterGroups(emptyPreviewFilters()), []);
});

test("the expanded calendar shares a range across months and keeps draft dates local until Apply", async () => {
  const page = await mount("date"); const trigger = page.host.querySelector("button")!;
  const original = trigger.textContent;
  await page.click(trigger);
  assert.equal(document.querySelectorAll('table[role="grid"]').length, 2);
  await page.click(document.querySelector('[data-day="2026-10-30"]'));
  await page.click(document.querySelector('[data-day="2026-11-03"]'));
  assert.equal(document.querySelector<HTMLInputElement>('input[type="date"]')!.value, "2026-10-30");
  assert.equal([...document.querySelectorAll<HTMLInputElement>('input[type="date"]')][1].value, "2026-11-03");
  await page.escape(); assert.equal(trigger.textContent, original);
  await page.click(trigger);
  await page.click(document.querySelector('[data-day="2026-10-30"]'));
  await page.click(document.querySelector('[data-day="2026-11-03"]'));
  await page.click(page.button("Aplicar"));
  assert.notEqual(trigger.textContent, original);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(document.activeElement, trigger);
});
