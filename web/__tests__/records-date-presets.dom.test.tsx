import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { Period } from "@/components/business-app/business-format";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; });

const pad = (value: number) => String(value).padStart(2, "0");
const iso = (year: number, month: number, day: number) => `${year}-${pad(month)}-${pad(day)}`;
const typed = (day: string) => `${day.slice(8)}/${day.slice(5, 7)}/${day.slice(0, 4)}`;
const now = new Date();
const year = now.getFullYear();
const month = now.getMonth() + 1;
const wholeMonth = (shift: number) => {
  const first = new Date(year, month - 1 + shift, 1);
  const last = new Date(year, month + shift, 0);
  return { from: iso(first.getFullYear(), first.getMonth() + 1, 1), to: iso(last.getFullYear(), last.getMonth() + 1, last.getDate()) };
};
const WHOLE = { "Este mes": wholeMonth(0), "Mes pasado": wholeMonth(-1), "Este año": { from: iso(year, 1, 1), to: iso(year, 12, 31) } } as const;
const KIND = { "Este mes": "this_month", "Mes pasado": "last_month", "Este año": "this_year" } as const;

async function mount(width: number, connected: boolean) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const DatePreview = (await import("@/components/business-app/transacciones/RecordsDatePreview")).default;
  const presets: string[] = [];
  const changes: Period[] = [];
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><DatePreview period={{ key: "custom", from: "2026-10-01", to: "2026-10-25" }} onChange={(next) => changes.push(next)} onPreset={connected ? (kind) => presets.push(kind) : undefined} /></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  const click = (node: Element | null | undefined) => act(async () => { assert.ok(node); (node as HTMLElement).click(); });
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === text);
  const list = () => [...document.querySelectorAll<HTMLButtonElement>('[aria-label="Períodos rápidos"] button')].map((node) => node.textContent);
  const fields = () => [...document.querySelectorAll<HTMLInputElement>('[data-testid="range-picker"] input')].map((input) => input.value);
  await click(host.querySelector("button"));
  return { host, click, button, list, fields, presets, changes };
}

for (const width of [1440, 390]) {
  test(`one list of presets is the only preset control at ${width}px`, async () => {
    const page = await mount(width, true);
    const expected = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 30 días", "Este mes", "Mes pasado", "Trimestre anterior", "Este año", "Todo", "Personalizado"];
    assert.deepEqual(page.list(), width === 390 ? expected.filter((name) => name !== "Hoy") : expected);
    for (const name of ["Todo", "Este mes", "Mes pasado"]) assert.equal([...document.querySelectorAll("button")].filter((node) => node.textContent === name).length, 1, `${name} appears once`);
    assert.equal(page.button(String(year)), undefined, "the year chip is gone");
  });

  for (const name of Object.keys(WHOLE) as (keyof typeof WHOLE)[]) test(`${name} selects its dates and asks for the ${KIND[name]} report at ${width}px`, async () => {
    const page = await mount(width, true);
    await page.click(page.button(name));
    assert.deepEqual(page.fields(), [typed(WHOLE[name].from), typed(WHOLE[name].to)]);
    assert.deepEqual(page.presets, [], "choosing a preset only selects dates");
    await page.click(page.button("Confirmar período"));
    assert.deepEqual(page.presets, [KIND[name]]);
    assert.deepEqual(page.changes, []);
  });

  test(`Todo clears the range and asks for every date at ${width}px`, async () => {
    const page = await mount(width, true);
    await page.click(page.button("Todo"));
    assert.deepEqual(page.fields(), ["", ""]);
    assert.equal(document.querySelectorAll('[data-testid="range-picker"] td[aria-selected="true"]').length, 0);
    await page.click(page.button("Confirmar período"));
    assert.deepEqual(page.presets, ["all"]);
    assert.deepEqual(page.changes, []);
  });

  test(`a range that is not a whole period stays a custom range at ${width}px`, async () => {
    const page = await mount(width, true);
    await page.click(page.button("Últimos 7 días"));
    await page.click(page.button("Confirmar período"));
    assert.deepEqual(page.presets, []);
    assert.equal(page.changes.length, 1);
    assert.equal(page.changes[0].key, "custom");
  });
}

test("a picker without a report behind it gets the same dates and an all-dates period", async () => {
  const page = await mount(1440, false);
  await page.click(page.button("Mes pasado"));
  await page.click(page.button("Confirmar período"));
  assert.deepEqual(page.changes.map(({ key, from, to }) => ({ key, from, to })), [{ key: "custom", ...WHOLE["Mes pasado"] }]);
  await page.click(page.host.querySelector("button"));
  await page.click(page.button("Todo"));
  await page.click(page.button("Confirmar período"));
  assert.equal(page.changes.at(-1)?.key, "all");
});
