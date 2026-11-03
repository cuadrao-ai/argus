import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { periodRange, todayIso, wholePeriod, type Period } from "@/components/business-app/business-format";
import { keepOwnListSearch } from "./fixtures/own-list-search";

await keepOwnListSearch();

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });
let cleanup = async () => {};
afterEach(async () => { await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; });

const typed = (day: string) => `${day.slice(8)}/${day.slice(5, 7)}/${day.slice(0, 4)}`;
const today = todayIso();
const year = today.slice(0, 4);
const WHOLE = {
  "Este mes": { key: "this_month", ...wholePeriod("this_month", today) },
  "Mes pasado": { key: "last_month", ...wholePeriod("last_month", today) },
  "Este año": { key: "this_year", ...wholePeriod("this_year", today) },
} as const;
const LABEL = { "Este mes": "Este mes", "Mes pasado": "Mes pasado", "Este año": year } as const;

async function mount(width: number, period: Period) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 844 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const DatePreview = (await import("@/components/business-app/transacciones/RecordsDatePreview")).default;
  const changes: Period[] = [];
  function Page() {
    const [value, setValue] = useState(period);
    return <DatePreview period={period} value={value} onChange={(next) => { changes.push(next); setValue(next); }} />;
  }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Page /></I18nextProvider>));
  cleanup = async () => { await act(async () => root.unmount()); };
  const click = (node: Element | null | undefined) => act(async () => { assert.ok(node); (node as HTMLElement).click(); });
  const button = (text: string) => [...(document.querySelector('[data-testid="range-picker"]') ?? document).querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === text);
  const list = () => [...document.querySelectorAll<HTMLButtonElement>('[aria-label="Períodos rápidos"] button')].map((node) => node.textContent);
  const pressed = () => [...document.querySelectorAll<HTMLButtonElement>('[aria-label="Períodos rápidos"] button[aria-pressed="true"]')].map((node) => node.textContent);
  const fields = () => [...document.querySelectorAll<HTMLInputElement>('[data-testid="range-picker"] input')].map((input) => input.value);
  const trigger = () => host.querySelector("button")!.textContent;
  await click(host.querySelector("button"));
  return { host, click, button, list, pressed, fields, trigger, changes };
}

const custom: Period = { key: "custom", from: "2026-10-01", to: "2026-10-25" };

for (const width of [1440, 390]) {
  test(`one list of presets is the only preset control at ${width}px`, async () => {
    const page = await mount(width, custom);
    const expected = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 30 días", "Este mes", "Mes pasado", "Trimestre anterior", "Este año", "Todo", "Personalizado"];
    assert.deepEqual(page.list(), width === 390 ? expected.filter((name) => name !== "Hoy") : expected);
    for (const name of ["Todo", "Este mes", "Mes pasado"]) assert.equal([...document.querySelectorAll("button")].filter((node) => node.textContent === name).length, 1, `${name} appears once`);
    assert.equal(page.button(year), undefined, "the year chip is gone");
  });

  for (const name of Object.keys(WHOLE) as (keyof typeof WHOLE)[]) {
    test(`${name} opens highlighted with its dates when it is the current period at ${width}px`, async () => {
      const page = await mount(width, { key: WHOLE[name].key, from: WHOLE[name].from, to: WHOLE[name].to });
      assert.deepEqual(page.pressed(), [name]);
      assert.deepEqual(page.fields(), [typed(WHOLE[name].from), typed(WHOLE[name].to)]);
    });

    test(`${name} selects its dates, and Confirmar names the whole period at ${width}px`, async () => {
      const page = await mount(width, custom);
      await page.click(page.button(name));
      assert.deepEqual(page.fields(), [typed(WHOLE[name].from), typed(WHOLE[name].to)]);
      assert.deepEqual(page.changes, [], "choosing a preset only selects dates");
      await page.click([...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === "Confirmar período"));
      assert.deepEqual(page.changes, [WHOLE[name]]);
      assert.equal(page.trigger(), LABEL[name]);
    });
  }

  test(`the sample page's own this-month period opens on Este mes at ${width}px`, async () => {
    const page = await mount(width, periodRange("this_month"));
    assert.deepEqual(page.pressed(), ["Este mes"]);
    assert.deepEqual(page.fields(), [typed(WHOLE["Este mes"].from), typed(WHOLE["Este mes"].to)]);
  });

  test(`Todo is the current period when nothing is limited, and clears the range at ${width}px`, async () => {
    const page = await mount(width, periodRange("all"));
    assert.deepEqual(page.pressed(), ["Todo"]);
    assert.deepEqual(page.fields(), ["", ""]);
    await page.click(page.button("Mes pasado"));
    await page.click(page.button("Todo"));
    assert.deepEqual(page.fields(), ["", ""]);
    assert.equal(document.querySelectorAll('[data-testid="range-picker"] td[aria-selected="true"]').length, 0);
    await page.click([...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === "Confirmar período"));
    assert.deepEqual(page.changes.map((change) => change.key), ["all"]);
    assert.equal(page.trigger(), "Todo");
  });

  test(`Personalizado is highlighted only for a range that matches no preset at ${width}px`, async () => {
    const page = await mount(width, custom);
    assert.deepEqual(page.pressed(), ["Personalizado"]);
    assert.deepEqual(page.fields(), [typed("2026-10-01"), typed("2026-10-25")]);
  });

  test(`a range that is not a whole period stays custom and is named by its dates at ${width}px`, async () => {
    const page = await mount(width, periodRange("all"));
    await page.click(page.button("Últimos 7 días"));
    await page.click([...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === "Confirmar período"));
    assert.equal(page.changes.length, 1);
    assert.equal(page.changes[0].key, "custom");
    assert.match(page.trigger() ?? "", /–/);
  });
}
