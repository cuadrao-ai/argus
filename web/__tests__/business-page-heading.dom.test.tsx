import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
});
let cleanup = async () => {};
afterEach(async () => { await cleanup(); cleanup = async () => {}; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const titles = {
  inbox: "business.inbox.title",
  transactions: "business.transactions.title",
  activity: "business.nav.activity",
  invoicing: "business.invoicing_preview.title",
  business: "business.settings.title",
} as const;

async function mount(screen: keyof typeof titles, width: number, catalog: typeof spanish | typeof english) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "test", resources: { test: { translation: catalog } }, interpolation: { escapeValue: false } });
  const { PageHeading } = await import("@/components/business-app/foundation/PageHeading");
  const BusinessHeader = (await import("@/components/business-app/foundation/BusinessHeader")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const context = {
    actions: { create: [], composer: [], starterEntries: [] }, chosen: null, source: {}, revision: 0,
    records: { workspace: null }, openPanel: () => {},
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  cleanup = async () => { await act(async () => root.unmount()); host.remove(); };
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>
    {width < 720 ? <PageHeading screen={screen} /> : <BusinessHeader home={false} name={null} screen={screen} />}
  </BusinessContext.Provider></I18nextProvider>));
  return { host, title: i18n.t(titles[screen]), intro: i18n.t("business.page_intro.business") };
}

for (const [language, catalog] of Object.entries({ es: spanish, en: english })) {
  describe(`${language} page headings`, () => {
    for (const width of [390, 768, 1440]) {
      for (const screen of Object.keys(titles) as (keyof typeof titles)[]) {
        test(`${screen} at ${width}px keeps its title and only Business settings has an intro`, async () => {
          const page = await mount(screen, width, catalog);
          assert.equal(page.host.querySelector("h1, h2")?.textContent, page.title);
          const description = page.host.querySelector('[data-testid="business-page-description"]');
          if (screen === "business") {
            assert.equal(description?.textContent, page.intro);
            assert.ok(description?.querySelector('span[aria-hidden="true"] svg'));
          } else {
            assert.ok(description === null, "intro description must be absent");
            assert.ok(page.host.querySelector("p, svg") === null, "no intro text or icon remains");
            if (width >= 720) assert.equal(document.body.style.getPropertyValue("--workspace-bar"), "", "title-only screens retain the normal bar");
          }
        });
      }
    }
    test("only the Business settings intro remains in the catalog", () => {
      const intro = catalog.business.page_intro;
      assert.deepEqual(Object.keys(intro), ["business"]);
      assert.ok(intro.business);
    });
  });
}
