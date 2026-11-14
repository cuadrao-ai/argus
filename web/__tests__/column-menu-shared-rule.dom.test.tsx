import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { defaultReceptionPreferences, receptionLayout } from "@/components/business-app/recepcion/reception-columns";
import { sampleRecordsPreferences } from "@/components/business-app/transacciones/sample-records-preferences";
import { isLastShownColumn, recordsColumnSettings, toggleRecordsColumn, type ColumnLayout } from "@/components/business-app/transacciones/records-view-preferences";

let cleanup = async () => {};
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 1000 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await cleanup(); cleanup = async () => {}; (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const SCREENS: Record<string, () => ColumnLayout> = { Registros: sampleRecordsPreferences, Bandeja: () => receptionLayout(defaultReceptionPreferences(), "all") };

async function mountMenu(initial: ColumnLayout) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const Menu = (await import("@/components/business-app/transacciones/RecordsSettingsPreview")).default;
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  const { useState } = await import("react");
  let value = initial;
  function Harness() {
    const [layout, setLayout] = useState(initial);
    value = layout;
    return <Menu value={layout} onChange={setLayout} onRestore={() => {}} />;
  }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>); });
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await act(async () => host.querySelector<HTMLButtonElement>('[data-testid="transacciones-view-options"]')!.click());
  const box = (key: string) => document.querySelector<HTMLInputElement>(`[data-column-setting="${key}"] input[type="checkbox"]`)!;
  return { value: () => value, box, click: (key: string) => act(async () => box(key).click()) };
}

for (const [screen, layout] of Object.entries(SCREENS)) {
  test(`${screen}: no column is locked by name, and hiding stops at the last column a tab shows`, async () => {
    const menu = await mountMenu(layout());
    const keys = menu.value().order;
    assert.equal(document.querySelectorAll("[data-column-setting]").length, keys.length);
    assert.equal(document.querySelector('[role="dialog"] svg.lucide-lock-keyhole'), null);
    for (const key of keys) assert.equal(menu.box(key).disabled, isLastShownColumn(menu.value(), key), `${key} is free unless it is the last one shown`);
    // Every column takes a turn as the one left standing.
    for (const survivor of keys) {
      let value = layout();
      if (value.hidden.includes(survivor)) value = toggleRecordsColumn(value, survivor);
      for (const key of keys) if (key !== survivor && !value.hidden.includes(key)) value = toggleRecordsColumn(value, key);
      const families = new Set(value.columns.flatMap(column => column.families));
      const shown = recordsColumnSettings(value).filter(column => column.shown);
      for (const family of families) assert.ok(shown.some(column => column.families.includes(family)), `${survivor} last: ${family} keeps a column`);
      for (const column of shown) if (shown.every(other => other === column || !column.families.some(family => other.families.includes(family)))) assert.equal(toggleRecordsColumn(value, column.key), value, `${column.key} is refused`);
    }
  });

  test(`${screen}: the menu disables the box the rule refuses and leaves the layout as it was`, async () => {
    const menu = await mountMenu(layout());
    const shown = () => recordsColumnSettings(menu.value()).filter(column => column.shown).map(column => column.key);
    for (let turn = 0; turn < 40; turn++) {
      const next = shown().find(key => !menu.box(key).disabled);
      if (!next) break;
      await menu.click(next);
    }
    const left = shown();
    assert.ok(left.length >= 1);
    for (const key of left) {
      assert.equal(menu.box(key).disabled, true);
      const before = menu.value();
      await menu.click(key);
      assert.equal(menu.value(), before);
    }
  });
}
