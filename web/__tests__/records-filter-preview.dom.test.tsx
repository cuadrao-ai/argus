import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { activeFilterGroups, emptyPreviewFilters, validPreviewAmount, type PreviewFilters } from "@/components/business-app/transacciones/records-filter-preview-model";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; });

async function mount(kind: "filters" | "date" | "toolbar", width = 1440, initialFilters = emptyPreviewFilters("DOP")) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const Filters = (await import("@/components/business-app/transacciones/RecordsFiltersPreview")).default;
  const { RecordsToolbar } = await import("@/components/business-app/transacciones/RecordsToolbar");
  const DatePreview = (await import("@/components/business-app/transacciones/RecordsDatePreview")).default;
  const RecordsTypeTabs = (await import("@/components/business-app/transacciones/RecordsTypeTabs")).default;
  function FilterHarness() {
    const [value, setValue] = useState<PreviewFilters>(initialFilters);
    const recordKind = "gasto";
    return <><Filters options={null} value={value} onChange={setValue} /><output data-testid="applied-record-kind">{recordKind}</output><output data-testid="applied-filters">{JSON.stringify(value)}</output></>;
  }
  function ToolbarHarness() {
    const [record, setRecord] = useState<{ query: string; kind: "gasto" | "venta" }>({ query: "", kind: "gasto" });
    const [filters, setFilters] = useState(initialFilters);
    return <><RecordsTypeTabs value={record.kind} onChange={(kind) => setRecord({ ...record, kind })} /><RecordsToolbar appliedFilters={filters} onFiltersChange={setFilters} filter={record} onChange={setRecord} options={null} period={{ key: "custom", from: "2026-10-01", to: "2026-10-25" }} setPeriod={() => {}} /><output data-testid="applied-record-kind">{record.kind}</output><output data-testid="applied-filters">{JSON.stringify(filters)}</output></>;
  }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}>{kind === "toolbar" ? <ToolbarHarness /> : kind === "filters" ? <FilterHarness /> : <DatePreview period={{ key: "custom", from: "2026-10-01", to: "2026-10-25" }} />}</I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  const click = (node: Element | null | undefined) => act(async () => { assert.ok(node); (node as HTMLElement).click(); });
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent?.replaceAll("•", "") === text || text === "Filtros" && node.textContent?.startsWith("Filtros"));
  const escape = () => act(async () => { document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  return { act, host, click, button, escape };
}

test("filter draft is discarded on Escape, committed by Apply, and removable by group", async () => {
  const page = await mount("filters");
  await page.click(page.button("Filtros"));
  await page.click(page.button("Datos fiscales"));
  await page.click([...document.querySelectorAll("label")].find((label) => label.textContent === "Faltan datos")?.querySelector("input"));
  await page.escape();
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent, "");
  await page.click(page.button("Filtros"));
  await page.click(page.button("Datos fiscales"));
  assert.equal([...document.querySelectorAll("label")].find((label) => label.textContent === "Faltan datos")!.querySelector<HTMLInputElement>("input")!.checked, false);
  await page.click([...document.querySelectorAll("label")].find((label) => label.textContent === "Faltan datos")?.querySelector("input"));
  await page.click(page.button("Adjunto"));
  await page.click([...document.querySelectorAll("label")].find((label) => label.textContent === "Sin documento"));
  await page.click(page.button("Aplicar"));
  const chips = document.querySelector('[data-testid="records-preview-filter-chips"]')!;
  assert.match(chips.textContent ?? "", /Faltan datos/);
  assert.match(chips.textContent ?? "", /Sin documento/);
  assert.equal(page.host.querySelector('button[aria-haspopup="dialog"]')?.textContent, "Filtros2");
  await page.click(document.querySelector('button[aria-label="Quitar filtro Datos fiscales"]'));
  assert.doesNotMatch(chips.textContent ?? "", /Faltan datos/);
  await page.click(page.button("Limpiar filtros"));
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent, "");
});

test("amount controls have one currency and exact validation rejects an inverted range", async () => {
  const page = await mount("filters"); await page.click(page.button("Filtros")); await page.click(page.button("Monto"));
  assert.ok([...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')].every((input) => !input.disabled));
  assert.ok([...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')].every((input) => !input.disabled));
  assert.equal(validPreviewAmount({ currency: "USD", min: "9007199254740993.01", max: "9007199254740993.00" }), false);
  assert.deepEqual(activeFilterGroups(emptyPreviewFilters("DOP")), []);
  assert.equal(validPreviewAmount({ currency: "USD", min: "1234567890123456", max: "" }), false);
});

for (const width of [1440, 390]) for (const clearFrom of ["editor", "chips"]) test(`clearing filters from ${clearFrom} keeps one currency and clears amount bounds at ${width}px`, async () => {
  const page = await mount("filters", width, emptyPreviewFilters("DOP"));
  await page.click(page.button("Filtros"));
  await page.click(page.button("Monto"));
  const fields = [...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')];
  for (const [index, value] of ["100", "200"].entries()) await page.act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(fields[index], value);
    fields[index].dispatchEvent(new Event("input", { bubbles: true }));
  });
  if (clearFrom === "chips") await page.click(page.button("Aplicar"));
  await page.click(page.button("Limpiar filtros"));
  if (clearFrom === "chips") {
    await page.click(page.button("Filtros"));
    await page.click(page.button("Monto"));
  }
  assert.ok([...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')].every((input) => input.value === ""));
  await page.click(page.button("Aplicar"));
  assert.deepEqual(JSON.parse(document.querySelector('[data-testid="applied-filters"]')!.textContent!), emptyPreviewFilters("DOP"));
});

for (const width of [1440, 390]) test(`amount entry preserves valid values on invalid input at ${width}px`, async () => {
  const page = await mount("filters", width, emptyPreviewFilters("USD"));
  await page.click(page.button("Filtros")); await page.click(page.button("Monto"));
  const fields = [...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')];
  const type = (field: HTMLInputElement, text: string) => page.act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, text);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await type(fields[0], "0"); assert.equal(fields[0].value, "0");
  await type(fields[0], "1234567890123456");
  assert.equal(fields[0].value, "0"); assert.equal(fields[0].getAttribute("aria-invalid"), "true");
  assert.match(document.getElementById(fields[0].getAttribute("aria-describedby")!)!.textContent!, /15/);
  await type(fields[0], "1000.25"); assert.equal(fields[0].value, "1,000.25");
  await type(fields[0], "1000.251"); assert.equal(fields[0].value, "1,000.25");
  await type(fields[0], "1000.25");
  await type(fields[1], "500"); assert.equal(page.button("Aplicar")!.disabled, true);
  await type(fields[1], "2000"); assert.equal(page.button("Aplicar")!.disabled, false);
  await page.click(page.button("Aplicar"));
  assert.match(document.querySelector('[data-testid="records-preview-filter-chips"]')!.textContent!, /USD.*1000.25.*2000/);
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

test("phone uses the full viewport, vertical months, one Hoy in the list and safe opening focus", async () => {
  const page = await mount("date", 390); await page.click(page.host.querySelector("button"));
  const sheet = document.querySelector<HTMLElement>('[role="dialog"]')!;
  assert.equal(sheet.dataset.fullScreen, "true"); assert.equal(sheet.style.height, "844px");
  assert.equal(document.querySelectorAll('table[role="grid"]').length, 12);
  assert.equal([...document.querySelectorAll("button")].filter((button) => button.textContent === "Hoy").length, 1);
  assert.ok(document.querySelector('[aria-label="Períodos rápidos"] button') && [...document.querySelectorAll('[aria-label="Períodos rápidos"] button')].some((button) => button.textContent === "Hoy"), "the one Hoy is in the list");
  assert.notEqual(document.activeElement?.tagName, "INPUT"); assert.ok(page.button("Confirmar período"));
  await page.escape(); assert.equal(document.querySelector('[role="dialog"]'), null);
});


test("checkbox parents derive mixed/all/none from label clicks and bulk changes", async () => {
  const page = await mount("filters"); await page.click(page.button("Filtros"));
  await page.click([...document.querySelectorAll('[role="tab"]')].find((node) => node.textContent?.startsWith("Cuenta")));
  const label = (text: string) => [...document.querySelectorAll("label")].find((node) => node.textContent === text)!;
  const parent = () => label("Seleccionar todo").querySelector<HTMLInputElement>("input")!;
  assert.equal(parent().checked, false); assert.equal(parent().indeterminate, false);
  await page.click(label("Cuenta corriente"));
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

for (const width of [1440, 390]) for (const clearFrom of ["editor", "chips"]) test(`tabs share optional filters and Clear keeps sales and USD at ${width}px from ${clearFrom}`, async () => {
  const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  try {
    const page = await mount("toolbar", width, emptyPreviewFilters("USD"));
    assert.equal(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent, "Compras");
    await page.click(page.button("Ventas"));
    await page.click(page.button("Filtros")); await page.click(page.button("Adjunto"));
    await page.click([...document.querySelectorAll("label")].find((label) => label.textContent === "Sin documento"));
    await page.click(page.button("Aplicar"));
    await page.click(page.button("Compras"));
    assert.match(document.querySelector('[data-testid="records-preview-filter-chips"]')!.textContent!, /Sin documento/);
    await page.click(page.button("Ventas"));
    if (clearFrom === "editor") await page.click(page.button("Filtros"));
    await page.click([...document.querySelectorAll<HTMLButtonElement>(clearFrom === "editor" ? '[role="dialog"] button' : '[data-testid="records-preview-filter-chips"] button')].find(node => node.textContent === "Limpiar filtros"));
    if (clearFrom === "editor") await page.click(page.button("Aplicar"));
    assert.equal(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent, "Ventas");
    assert.deepEqual(JSON.parse(document.querySelector('[data-testid="applied-filters"]')!.textContent!), emptyPreviewFilters("USD"));
    assert.ok(document.querySelector('button[aria-label="Moneda: USD"]'));
    assert.equal(page.button("Filtros")!.textContent, "Filtros");
    await page.click(page.button("Filtros"));
    assert.equal(document.querySelector('[data-group="record"]'), null);
    assert.equal(document.querySelector('input[name="records-currency"]'), null);
    assert.equal([...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(node => node.textContent === "Limpiar filtros")!.disabled, true);
    assert.equal(document.querySelector('[role="dialog"]')!.textContent!.includes("•"), false);
  } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
});

test("desktop kind lives in tabs and saved views restore its controlled value", async () => {
  const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  try {
    const page = await mount("toolbar");
    assert.equal(document.querySelector('button[aria-label^="Registro:"]'), null);
    assert.equal(document.querySelector('button[aria-label^="Tipo:"]'), null);
    const type = (field: HTMLInputElement, value: string) => page.act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value); field.dispatchEvent(new Event("input", { bubbles: true })); });
    const search = document.querySelector<HTMLInputElement>('input[type="search"]')!;
    await type(search, "Nube");
    await page.click(page.button("Compras"));
    await page.click(page.button("Vistas")); await page.click(page.button("Guardar vista"));
    await type(document.querySelector<HTMLInputElement>('[role="dialog"] input')!, "Gastos de Nube");
    await page.click(document.querySelector('[role="dialog"] button[type="submit"]'));
    await page.click(page.button("Ventas"));
    assert.equal(search.value, "Nube");
    await page.click(page.button("Vistas")); await page.click(page.button("Gastos de Nube"));
    assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
    assert.equal(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent, "Compras");
    await page.click(page.button("Limpiar búsqueda"));
    assert.equal(search.value, ""); assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
    assert.equal(page.button("Limpiar filtros"), undefined);
    assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
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
  await page.click(page.button("Cuenta"));
  assert.equal(document.activeElement, page.button("Todos los filtros"));
  const label = (text: string) => [...document.querySelectorAll("label")].find((node) => node.textContent === text)!;
  await page.click(label("Cuenta corriente"));
  assert.equal(label("Seleccionar todo").querySelector<HTMLInputElement>("input")!.indeterminate, true);
  await page.click(page.button("Todos los filtros"));
  assert.equal(document.activeElement?.getAttribute("data-group"), "account");
  await page.click(page.button("Adjunto")); await page.click(label("Sin documento"));
  await page.click(page.button("Todos los filtros")); await page.click(document.querySelector('[data-group="account"]'));
  assert.equal(label("Cuenta corriente").querySelector<HTMLInputElement>("input")!.checked, true);
  await page.click(page.button("Aplicar"));
  assert.equal(document.activeElement, trigger);
  assert.equal(document.querySelector('[data-testid="applied-record-kind"]')?.textContent, "gasto");
  await page.click(trigger); await page.click(document.querySelector('[data-group="account"]'));
  await page.click(label("Seleccionar todo"));
  assert.equal(label("Seleccionar todo").querySelector<HTMLInputElement>("input")!.checked, true);
  await page.escape(); await page.click(trigger); await page.click(document.querySelector('[data-group="account"]'));
  assert.equal(label("Seleccionar todo").querySelector<HTMLInputElement>("input")!.indeterminate, true);
  await page.click([...document.querySelectorAll('[role="dialog"] button')].find((node) => node.textContent === "Limpiar filtros")); await page.click(page.button("Aplicar"));
  assert.equal(document.querySelector('[data-testid="records-preview-filter-chips"]')?.textContent, "");
});


for (const width of [1440, 390]) test(`currency selector switches immediately, clears bounds and stays out of Filters at ${width}px`, async () => {
  const env = { NODE_ENV: process.env.NODE_ENV, NEXT_PUBLIC_MOCK_AUTH: process.env.NEXT_PUBLIC_MOCK_AUTH };
  Object.assign(process.env, { NODE_ENV: "development", NEXT_PUBLIC_MOCK_AUTH: "true" });
  try {
    const page = await mount("toolbar", width, { ...emptyPreviewFilters("USD"), amount: { currency: "USD", min: "200", max: "100" } });
    await page.click(document.querySelector('button[aria-label="Moneda: USD"]'));
    const currencyDialog = document.querySelector('[role="dialog"]')!;
    assert.equal(currencyDialog.querySelector('input[type="search"]'), null);
    assert.deepEqual([...currencyDialog.querySelectorAll("button")].filter(node => ["DOP", "USD", "EUR"].includes(node.textContent!)).map(node => node.textContent), ["DOP", "USD", "EUR"]);
    await page.click(page.button("EUR"));
    assert.deepEqual(JSON.parse(document.querySelector('[data-testid="applied-filters"]')!.textContent!).amount, { currency: "EUR", min: "", max: "" });
    await page.click(page.button("Filtros"));
    await page.click(page.button("Monto"));
    assert.equal(document.querySelector('input[name="records-currency"]'), null);
    assert.ok([...document.querySelectorAll<HTMLInputElement>('input[inputmode="decimal"]')].every(field => field.value === "" && field.getAttribute("aria-invalid") !== "true"));
    assert.equal(page.button("Aplicar")!.disabled, false);
  } finally { for (const [key, value] of Object.entries(env)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; } }
});

test("the desktop filter trigger toggles and Escape restores focus", async () => {
  const page = await mount("filters");
  const trigger = page.button("Filtros")!;
  await page.click(trigger); assert.ok(document.querySelector('[role="dialog"]'));
  await page.click(trigger); assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(document.activeElement, trigger);
  await page.click(trigger); await page.escape();
  assert.equal(document.querySelector('[role="dialog"]'), null);
  assert.equal(document.activeElement, trigger);
});
