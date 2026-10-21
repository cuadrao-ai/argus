import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 390, height: 844 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  document.body.innerHTML = "";
});

async function mount() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source = { ...fixture, receipt: async (id: string, signal?: AbortSignal) => ({ ...await fixture.receipt(id, signal), draft_id: dossierFixtureIds.fiscal }) };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    return <BusinessPanel />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  unmounts.push(() => act(async () => root.unmount()));
  const settle = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      if (done()) return;
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    }
    throw new Error(`timed out waiting for ${what}`);
  };
  return { host, settle, open: (next: Parameters<NonNullable<typeof api>["openPanel"]>[0]) => act(async () => api!.openPanel(next)) };
}

describe("the receipt detail page on a phone", () => {
  test("adds no space under the docked footer, so it sits on the bottom edge of the pane", async () => {
    const page = await mount();
    await page.open({ kind: "receipt", receiptId: "rcpt-ferreteria" });
    await page.settle(() => Boolean(page.host.querySelector('[data-testid="receipt-review-footer"]')), "the receipt footer");
    const column = page.host.querySelector<HTMLElement>("[data-column]");
    assert.ok(column);
    assert.ok(column.classList.contains("pb-0"), column.className);
    assert.ok(!column.classList.contains("pb-6"), column.className);
  });

  test("a list keeps its own breathing room under the last row", async () => {
    const page = await mount();
    await page.open({ kind: "inbox" });
    await page.settle(() => Boolean(page.host.querySelector("[data-column]")), "the list");
    assert.ok(page.host.querySelector<HTMLElement>("[data-column]")!.classList.contains("pb-6"));
  });
});
