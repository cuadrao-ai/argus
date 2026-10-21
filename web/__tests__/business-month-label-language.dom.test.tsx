import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "../components/business-app/BusinessWorkspace";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function render(language: "en" | "es-419", element: (modules: { MonthSwitcher: typeof import("../components/business-app/BusinessMonthClosePanel").MonthSwitcher; Panel: typeof import("../components/business-app/BusinessMonthClosePanel").default; useMonthCloseSource: typeof import("../components/business-app/BusinessMonthClosePanel").useMonthCloseSource }) => React.ReactNode) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const english = (await import("../public/locales/en/common.json")).default;
  const spanish = (await import("../public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("../components/business-app/BusinessWorkspace");
  const panel = await import("../components/business-app/BusinessMonthClosePanel");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { en: { translation: english }, "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const value = {
    source: { mode: "fixture" },
    chosen: { grant_id: "own-grant", capabilities: ["approve"], role: "owner", name: "Taller" },
    actions: { create: [] },
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={value}>{element({ MonthSwitcher: panel.MonthSwitcher, Panel: panel.default, useMonthCloseSource: panel.useMonthCloseSource })}</BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  for (let i = 0; i < 20; i += 1) {
    await act(async () => { await Promise.resolve(); });
  }
  return { act, host, root };
}

describe("the month label follows the shown language", () => {
  test("the switcher says October 2026 in English and Octubre 2026 in Spanish", async () => {
    for (const [language, label] of [["en", "October 2026"], ["es-419", "Octubre 2026"]] as const) {
      const { act, host, root } = await render(language, ({ MonthSwitcher }) => <MonthSwitcher month="2026-10" current="2026-10" earliest="2026-08" onMonth={() => {}} />);
      assert.equal(host.querySelector('[data-testid="month-close-month"]')?.textContent, label);
      await act(async () => { host.querySelector<HTMLButtonElement>('[data-testid="month-close-month"]')?.click(); });
      const options = [...document.querySelectorAll('[role="option"]')].map((option) => option.textContent);
      assert.ok(options.includes(label === "October 2026" ? "August 2026" : "Agosto 2026"), options.join(","));
      await act(async () => { root.unmount(); });
      host.remove();
    }
  });

  test("Inicio in English never shows a Spanish month", async () => {
    const { act, host, root } = await render("en", ({ Panel, useMonthCloseSource }) => {
      function Inicio() {
        return <Panel monthClose={useMonthCloseSource()} />;
      }
      return <Inicio />;
    });
    const label = host.querySelector('[data-testid="month-close-month"]')?.textContent ?? "";
    assert.match(label, /^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$/);
    await act(async () => { root.unmount(); });
    host.remove();
  });
});
