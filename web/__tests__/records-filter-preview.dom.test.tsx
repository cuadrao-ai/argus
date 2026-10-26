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

async function mount(kind: "filters" | "date" | "toolbar", width = 1440) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const Filters = (await import("@/components/business-app/transacciones/RecordsFiltersPreview")).default;
  const { RecordsToolbar } = await import("@/components/business-app/transacciones/RecordsToolbar");
  const DatePreview = (await import("@/components/business-app/transacciones/RecordsDatePreview")).default;
  function FilterHarness() {
    const [value, setValue] = useState(emptyPreviewFilters);
    const [recordKind, setRecordKind] = useState<"all" | "gasto" | "venta">("all");
    return <><Filters options={null} value={value} kind={recordKind} onChange={(next, nextKind) => { setValue(next); setRecordKind(nextKind); }} /><output data-testid="applied-record-kind">{recordKind}</output></>;
  }
  function ToolbarHarness() {
    const [record, setRecord] = useState<{ query: string; kind: "all" | "gasto" | "venta" }>({ query: "", kind: "all" });
    return <><RecordsToolbar filter={record} onChange={setRecord} options={null} period={{ key: "custom", from: "2026-10-01", to: "2026-10-25" }} setPeriod={() => {}} /><output data-testid="applied-record-kind">{record.kind}</output></>;
  }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{kind === "toolbar" ? <ToolbarHarness /> : kind === "filters" ? <FilterHarness /> : <DatePreview period={{ key: "custom", from: "2026-10-01", to: "2026-10-25" }} />}</I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  const click = (node: Element | null | undefined) => act(async () => { assert.ok(node); (node as HTMLElement).click(); });
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === text);
  const escape = () => act(async () => { document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  return { act, host, click, button, escape };
}

test("filter draft is discarded on Escape, committed by Apply, and removable by group", async () => {
  const page = await mount("filters");
  await page.click(page.button("Filtros"));
  await page.click(page.button("Revisión"));
  await page.click(document.querySelector('input[type="checkbox"]'));
  await page.escape();
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]'), null);
  await page.click(page.button("Filtros"));
  await page.click(page.button("Revisión"));
  assert.equal(document.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked, false);
  await page.click(document.querySelector('input[type="checkbox"]'));
  await page.click(page.button("Adjunto"));
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
  assert.equal(document.querySelector<HTMLInputElement>('input[type="text"]')!.value, "30/10/2026");
  assert.equal([...document.querySelectorAll<HTMLInputElement>('input[type="text"]')][1].value, "03/11/2026");
  await page.escape(); assert.equal(trigger.textContent, original);
  await page.click(trigger);
  await page.click(document.querySelector('[data-day="2026-10-30"]'));
  await page.click(document.querySelector('[data-day="2026-11-03"]'));
  await page.click(page.button("Confirmar período"));
  assert.notEqual(trigger.textContent, original);
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(document.activeElement, trigger);
});


test("typed dates validate on blur, repair live, and retain the visible month pair", async () => {
  const page = await mount("date"); await page.click(page.host.querySelector("button"));
  const fields = [...document.querySelectorAll<HTMLInputElement>('input[type="text"]')];
  const type = (field: HTMLInputElement, value: string) => page.act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.equal(fields[0].placeholder, "DD/MM/AAAA");
  assert.equal([...document.querySelectorAll("p, span")].some((node) => node.textContent === "DD/MM/AAAA"), false, "format is not repeated below the fields");
  await type(fields[0], "31/02/2026");
  assert.equal(fields[0].getAttribute("aria-invalid"), null);
  await page.act(async () => fields[0].dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
  assert.equal(fields[0].getAttribute("aria-invalid"), "true");
  assert.ok(fields[0].getAttribute("aria-describedby"));
  await type(fields[0], "28/10/2026"); await type(fields[1], "03/11/2026");
  assert.equal(fields[0].getAttribute("aria-invalid"), null);
  assert.ok(document.querySelector('[data-day="2026-10-28"]'));
  assert.ok(document.querySelector('[data-day="2026-11-03"]'));
  assert.equal(document.querySelector('input[type="date"]'), null);
});

test("keyboard cursor selects a range and Shift PageUp moves a year", async () => {
  const page = await mount("date"); await page.click(page.host.querySelector("button"));
  await page.act(async () => (document.querySelector('[data-day="2026-10-10"]') as HTMLElement).focus());
  const key = (key: string, shiftKey = false) => page.act(async () => document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key, shiftKey, bubbles: true })));
  await key("Enter"); await key("ArrowRight"); await key("Enter");
  const fields = [...document.querySelectorAll<HTMLInputElement>('input[type="text"]')];
  assert.equal(fields[0].value, "10/10/2026"); assert.equal(fields[1].value, "11/10/2026");
  await key("PageUp", true);
  assert.equal((document.activeElement as HTMLElement).dataset.day, "2025-10-11");
});

test("phone uses the full viewport, vertical months, one Today and safe opening focus", async () => {
  const page = await mount("date", 390); await page.click(page.host.querySelector("button"));
  const sheet = document.querySelector<HTMLElement>('[role="dialog"]')!;
  assert.equal(sheet.dataset.fullScreen, "true"); assert.equal(sheet.style.height, "844px");
  assert.equal(document.querySelectorAll('table[role="grid"]').length, 12);
  assert.equal([...document.querySelectorAll("button")].filter((button) => button.textContent === "Hoy").length, 1);
  assert.notEqual(document.activeElement?.tagName, "INPUT"); assert.ok(page.button("Confirmar período"));
  await page.escape(); assert.equal(document.querySelector('[role="dialog"]'), null);
});


test("checkbox parents derive mixed/all/none from label clicks and bulk changes", async () => {
  const page = await mount("filters"); await page.click(page.button("Filtros"));
  await page.click([...document.querySelectorAll('[role="tab"]')].find((node) => node.textContent?.startsWith("Revisión")));
  const label = (text: string) => [...document.querySelectorAll("label")].find((node) => node.textContent === text)!;
  const parent = () => label("Seleccionar todo").querySelector<HTMLInputElement>("input")!;
  assert.equal(parent().checked, false); assert.equal(parent().indeterminate, false);
  await page.click(label("Por revisar"));
  assert.equal(parent().indeterminate, true); assert.equal(parent().getAttribute("aria-checked"), "mixed");
  await page.click(label("Seleccionar todo"));
  assert.equal(parent().checked, true); assert.equal(parent().indeterminate, false);
  assert.ok([...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].every((input) => input.checked));
  await page.click(label("Seleccionar todo"));
  assert.ok([...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].every((input) => !input.checked));
});


test("bulk selection applies only to visible matches and keeps hidden choices", async () => {
  const page = await mount("filters"); await page.click(page.button("Filtros")); await page.click(page.button("Contraparte"));
  const label = (text: string) => [...document.querySelectorAll("label")].find((node) => node.textContent === text)!;
  await page.click(label("Nube Hosting"));
  const field = document.querySelector<HTMLInputElement>('input[type="search"]')!;
  const type = (value: string) => page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value); field.dispatchEvent(new Event("input", { bubbles: true })); });
  await type("Estación"); await page.click(label("Seleccionar resultados"));
  await type(""); assert.ok(label("Nube Hosting").querySelector<HTMLInputElement>("input")!.checked); assert.ok(label("Estación Ruta 3").querySelector<HTMLInputElement>("input")!.checked);
  await type("Estación"); await page.click(label("Seleccionar resultados"));
  await type(""); assert.ok(label("Nube Hosting").querySelector<HTMLInputElement>("input")!.checked); assert.equal(label("Estación Ruta 3").querySelector<HTMLInputElement>("input")!.checked, false);
  await type("no-such-option");
  const parent = label("Seleccionar resultados").querySelector<HTMLInputElement>("input")!;
  assert.equal(parent.checked, false); assert.equal(parent.indeterminate, false); assert.equal(parent.disabled, true);
});

test("record kind is drafted and applied with filters, counted and removable independently", async () => {
  const page = await mount("filters"); await page.click(page.button("Filtros"));
  assert.equal(document.querySelector('[role="tab"]')?.textContent, "Registro");
  const label = (text: string) => [...document.querySelectorAll("label")].find((node) => node.textContent === text)!;
  await page.click(label("Gasto"));
  assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "all");
  await page.escape(); await page.click(page.button("Filtros"));
  assert.equal(label("Gasto").querySelector<HTMLInputElement>("input")!.checked, false);
  await page.click(label("Gasto")); await page.click(page.button("Revisión")); await page.click(label("Por revisar")); await page.click(page.button("Aplicar"));
  assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
  assert.equal(page.host.querySelector('button[aria-haspopup="dialog"]')?.textContent, "Filtros2");
  await page.click(document.querySelector('button[aria-label="Quitar filtro Registro"]'));
  assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "all");
  assert.match(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent ?? "", /Por revisar/);
  await page.click(page.button("Limpiar filtros"));
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]'), null);
});


test("desktop kind lives in Filters and saved views restore its controlled value", async () => {
  const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  try {
    const page = await mount("toolbar");
    assert.equal(document.querySelector('button[aria-label^="Registro:"]'), null);
    assert.equal(document.querySelector('button[aria-label^="Tipo:"]'), null);
    const type = (field: HTMLInputElement, value: string) => page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value); field.dispatchEvent(new Event("input", { bubbles: true })); });
    const search = document.querySelector<HTMLInputElement>('input[type="search"]')!;
    await type(search, "Nube");
    await page.click(page.button("Filtros")); await page.click([...document.querySelectorAll("label")].find((label) => label.textContent === "Gasto")); await page.click(page.button("Aplicar"));
    await page.click(page.button("Vistas")); await page.click(page.button("Guardar vista"));
    await type(document.querySelector<HTMLInputElement>('[role="dialog"] input')!, "Gastos de Nube");
    await page.click(document.querySelector('[role="dialog"] button[type="submit"]'));
    await page.click(document.querySelector('button[aria-label="Quitar filtro Registro"]'));
    assert.equal(search.value, "Nube");
    await page.click(page.button("Vistas")); await page.click(page.button("Gastos de Nube"));
    assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
    assert.match(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent ?? "", /Registro · Gasto/);
    await page.click(page.button("Limpiar búsqueda"));
    assert.equal(search.value, ""); assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
    await page.click(page.button("Limpiar filtros"));
    assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "all");
    await cleanup();
    const phone = await mount("toolbar", 390);
    assert.equal(phone.host.querySelector('button[aria-label^="Tipo:"]'), null);
    assert.ok(phone.button("Filtros"));
  } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
});


test("phone filters keep one draft across group navigation and discard it on close", async () => {
  const page = await mount("filters", 390);
  const trigger = page.button("Filtros")!;
  await page.click(trigger);
  assert.equal(document.querySelector('[role="tablist"]'), null);
  await page.click(page.button("Revisión"));
  assert.equal(document.activeElement, page.button("Todos los filtros"));
  const label = (text: string) => [...document.querySelectorAll("label")].find((node) => node.textContent === text)!;
  await page.click(label("Por revisar"));
  assert.equal(label("Seleccionar todo").querySelector<HTMLInputElement>("input")!.indeterminate, true);
  await page.click(page.button("Todos los filtros"));
  assert.equal(document.activeElement?.getAttribute("data-group"), "review");
  await page.click(page.button("Registro")); await page.click(label("Gasto"));
  await page.click(page.button("Todos los filtros")); await page.click(document.querySelector('[data-group="review"]'));
  assert.equal(label("Por revisar").querySelector<HTMLInputElement>("input")!.checked, true);
  await page.click(page.button("Aplicar"));
  assert.equal(document.activeElement, trigger);
  assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
  await page.click(trigger); await page.click(document.querySelector('[data-group="review"]'));
  await page.click(label("Seleccionar todo"));
  assert.equal(label("Seleccionar todo").querySelector<HTMLInputElement>("input")!.checked, true);
  await page.escape(); await page.click(trigger); await page.click(document.querySelector('[data-group="review"]'));
  assert.equal(label("Seleccionar todo").querySelector<HTMLInputElement>("input")!.indeterminate, true);
  await page.click([...document.querySelectorAll('[role="dialog"] button')].find((node) => node.textContent === "Limpiar filtros")); await page.click(page.button("Aplicar"));
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]'), null);
});
