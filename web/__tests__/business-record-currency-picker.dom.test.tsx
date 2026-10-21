import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";

mock.module("next/navigation", () => ({
  usePathname: () => "/biz",
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

/** A workspace that works in pesos and Canadian dollars (the fixture accounts are pesos and US dollars), holding a receipt in euros. */
async function mount(target: { kind: "receipt"; id: string }, overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource>) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source: BusinessDataSource = {
    ...fixture,
    workspace: async () => ({ ...await fixture.workspace(), currencies: ["DOP", "CAD"] }),
    ...overrides(fixture),
  };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source}>
            <ReceiptReviewPanel target={target} />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (ready: () => boolean) => {
    for (let i = 0; i < 80 && !ready(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(ready(), "the page settled");
  };
  const idle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 300)); });
  return { host, act, settle, idle, close: () => act(async () => { root.unmount(); host.remove(); }) };
}

const optionTexts = (select: Element | null | undefined) => [...(select?.querySelectorAll("option") ?? [])].map((option) => option.textContent ?? "");

describe("the currency picker on a receipt", () => {
  test("offers the workspace currencies plus the receipt's own, on a receipt with no record yet", async () => {
    const view = await mount({ kind: "receipt", id: "rcpt-unknown" }, (fixture) => ({
      receipt: async (id, signal) => ({ ...await fixture.receipt(id, signal), currency: "EUR" }),
    }));
    try {
      await view.settle(() => [...view.host.querySelectorAll("select")].some((select) => optionTexts(select).includes("DOP")));
      await view.idle();
      const picker = [...view.host.querySelectorAll("select")].find((select) => optionTexts(select).includes("DOP"));
      assert.ok(picker, "the page has a currency picker");
      assert.deepEqual(optionTexts(picker).filter(Boolean).filter((text) => text !== "Elegir"), ["DOP", "CAD", "EUR"]);
    } finally { await view.close(); }
  });

  test("offers the same options when editing the currency of a prepared record", async () => {
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const view = await mount({ kind: "receipt", id: "rcpt-ferreteria" }, (fixture) => ({
      receipt: async (id, signal) => ({ ...await fixture.receipt(id, signal), draft_id: dossierFixtureIds.fiscal }),
      dossier: async (id) => {
        const dossier = structuredClone(await fixture.dossier(id));
        dossier.facts.currency = { state: "known", value: "EUR", origin: "extracted", verified: false, source_ids: [] };
        return dossier;
      },
    }));
    try {
      await view.settle(() => Boolean(view.host.querySelector('[data-fact="currency"] button')));
      const edit = view.host.querySelector<HTMLButtonElement>('[data-fact="currency"] button');
      assert.ok(edit);
      await view.idle();
      await view.act(async () => edit.click());
      const picker = view.host.querySelector('[data-testid="edit-currency"] select');
      assert.deepEqual(optionTexts(picker).filter(Boolean).filter((text) => text !== "Elegir"), ["DOP", "CAD", "EUR"]);
    } finally { await view.close(); }
  });
});
