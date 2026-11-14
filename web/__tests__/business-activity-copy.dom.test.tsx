import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { i18n } from "i18next";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { translate, type TestLanguage } from "./support/i18n-instance";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?activity=empty" });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
});
let cleanup = async () => {};
afterEach(async () => { await cleanup(); cleanup = async () => {}; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(i18n: i18n) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const ActivityDraft = (await import("@/components/business-app/actividad/ActivityDraft")).default;
  const context = { source: { mode: "fixture" }, chosen: null, openPanel: () => {} } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><ActivityDraft /></BusinessContext.Provider></I18nextProvider>,
  ));
  const empty = host.querySelector('[data-empty-kind="first_run"]');
  assert.ok(empty, "Actividad renders its first-run empty state");
  return { title: empty.querySelector("h3")?.textContent, body: empty.querySelector("p")?.textContent };
}

const WORDS: Record<TestLanguage, { title: string; body: string }> = {
  "es-419": {
    title: "Todavía no hay actividad",
    body: "Cuando alguien suba, revise o apruebe algo en este negocio, lo verás aquí.",
  },
  en: {
    title: "No activity yet",
    body: "When someone uploads, reviews or approves something in this business, you will see it here.",
  },
};

for (const language of ["es-419", "en"] as const) {
  test(`Actividad preserves its empty-state words in ${language}`, async () => {
    assert.deepEqual(await mount(await translate(language)), WORDS[language]);
  });

  test(`Actividad reads its empty state from the ${language} catalog`, async () => {
    const i18n = await translate(language);
    const catalog = structuredClone(i18n.getResourceBundle(language, "translation"));
    i18n.removeResourceBundle(language, "translation");
    i18n.addResourceBundle(language, "translation", catalog);
    const replacement = { title: `title-${language}`, body: `body-${language}` };
    i18n.addResource(language, "translation", "business.activity_feed.first_run_title", replacement.title);
    i18n.addResource(language, "translation", "business.activity_feed.first_run_body", replacement.body);
    assert.deepEqual(await mount(i18n), replacement);
  });
}
