import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptDetail } from "@/lib/business-api";

mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(""), useRouter: () => ({ push: () => undefined, replace: () => undefined }), usePathname: () => "/biz" }));
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  (await import("@/components/business-app/foundation/toasts")).clearToasts();
  document.body.innerHTML = "";
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(prepared: boolean, width: number) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const fixture = (await import("@/components/business-app/fixture-data")).createFixtureBusinessDataSource({ chatAvailable: false });
  const summaries = await fixture.receipts("all");
  const seed = await fixture.receipt(prepared ? summaries.find(row => row.draft_id)!.id : "rcpt-blurry");
  const arrivals: ReceiptDetail[] = Array.from({ length: 28 }, (_, index) => ({
    ...seed, id: `origin-${index}`, merchant: `Recibo sintético ${index}`, filename: `recibo-${index}.jpg`,
    received_at: new Date(Date.UTC(2026, 9, 28, 12, 0, -index)).toISOString(), channel: "web",
    activity: { state: "ready", unread: false, completion_cursor: null },
    bandeja: { por_revisar: true, leyendo: false, con_problema: false },
    bandeja_group: { group: "attention", reason: "missing_ncf", draft_id: seed.draft_id, version: seed.version },
  }));
  const outside: ReceiptDetail = { ...arrivals[0], id: "outside-tab", merchant: "Fuera de la pestaña", bandeja_group: { group: "listo", reason: null, draft_id: seed.draft_id, version: seed.version } };
  const inbox = [outside, ...arrivals.toReversed()];
  const activity = (await fixture.receiptPage!("all")).activity;
  const source = { ...fixture, receipts: async () => inbox, receiptPage: async () => ({ items: inbox, activity }), emailDeliveries: async () => [], receipt: async (id: string) => {
    const receipt = inbox.find(row => row.id === id); assert.ok(receipt); return receipt;
  } };
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } }, interpolation: { escapeValue: false } });
  (await import("@/lib/business-grant")).setChosenGrant(null);
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() { api = useBusiness(); return <BusinessPanel />; }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const wait = async (ready: () => boolean) => {
    if (ready()) return;
    for (let attempt = 0; attempt < 80; attempt++) {
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)); });
      if (ready()) return;
    }
    throw new Error("Expected receipt navigation state did not appear");
  };
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><Probe /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>));
  await act(async () => api!.openPanel({ kind: "inbox" }));
  // Rows can arrive before the directory. Choosing the Business remounts its
  // list, so wait for that scope before entering filters or search text.
  await wait(() => api!.chosen !== null && host.querySelector('[data-testid="reception-row"]') !== null);
  const click = async (node: HTMLElement | null | undefined) => { assert.ok(node); await act(async () => node.click()); };
  await click(host.querySelector("#reception-tab-attention"));
  const place = () => document.querySelector<HTMLElement>('[data-testid="receipt-place"]');
  const next = () => place()?.querySelectorAll<HTMLButtonElement>("button")[1];
  const previous = () => place()?.querySelectorAll<HTMLButtonElement>("button")[0];
  const openFirst = async () => { await click(host.querySelector('[data-testid="reception-row"] button.rowAction')); await wait(() => place() !== null); };
  return { host, act, click, openFirst, wait, place, next, previous, api: () => api!, cleanup: async () => { await act(async () => root.unmount()); host.remove(); } };
}

for (const prepared of [false, true]) for (const width of [1440, 390]) {
  test(`a filtered receipt drawer has one item, prepared=${prepared}, width=${width}`, async () => {
    const page = await mount(prepared, width);
    try {
      const findButton = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find(node => node.textContent === text);
      await page.click(findButton("Filtros"));
      if (width < 1024) await page.click(document.querySelector('[data-group="source"]'));
      const manual = [...document.querySelectorAll("label")].find(node => node.textContent === "Carga manual")?.querySelector("input");
      await page.click(manual);
      await page.click(findButton("Aplicar"));
      const searchField = () => page.host.querySelector<HTMLInputElement>('input[type="search"]');
      if (width < 1024) await page.wait(() => searchField() !== null);
      const search = searchField();
      await page.act(async () => {
        if (search) {
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(search, "recibo-27.jpg");
          search.dispatchEvent(new Event("input", { bubbles: true }));
        } else {
          assert.ok(width >= 1024, "a phone searches through the list field");
          (await import("@/components/business-app/foundation/list-search")).applyListSearch("inbox", "recibo-27.jpg");
        }
      });
      const rows = () => page.host.querySelectorAll('[data-testid="reception-row"]').length;
      await page.wait(() => rows() === 1);
      assert.equal(rows(), 1);
      await page.openFirst();
      await page.wait(() => page.place()?.textContent === "1 de 1");
      assert.equal(page.place()?.textContent, "1 de 1");
      assert.equal(page.next()?.disabled, true);
      assert.equal(page.previous()?.disabled, true);
    } finally { await page.cleanup(); }
  });

  test(`receipt navigation follows all 28 tab rows in display order, prepared=${prepared}, width=${width}`, async () => {
    const page = await mount(prepared, width);
    try {
      await page.openFirst();
      await page.wait(() => page.place()?.textContent === "1 de 28");
      const origin = page.api().panel;
      assert.equal(origin.kind, "receipt");
      if (origin.kind !== "receipt") throw new Error("Expected an open receipt");
      const expectedIds = Array.from({ length: 28 }, (_, index) => `origin-${index}`);
      assert.deepEqual(origin.receiptIds, expectedIds);

      // Check every transition against the list's actual navigation snapshot,
      // without rendering the full dossier 28 times in each viewport.
      const { receiptNavigationActions, receiptPlace } = await import("@/components/business-app/BusinessReviewShortcuts");
      let receiptId = origin.receiptId;
      for (let index = 0; index < expectedIds.length; index++) {
        assert.equal(receiptId, expectedIds[index]);
        assert.deepEqual(receiptPlace(receiptId, origin.receiptIds!), { index: index + 1, total: 28 });
        const moves = receiptNavigationActions(receiptId, origin.receiptIds!, (id) => { receiptId = id; });
        assert.equal(Boolean(moves.next), index < 27);
        assert.equal(Boolean(moves.previous), index > 0);
        moves.next?.();
      }

      const expectPosition = async (index: number) => {
        await page.wait(() => page.place()?.textContent === `${index + 1} de 28`);
        assert.equal(page.place()?.textContent, `${index + 1} de 28`);
        const panel = page.api().panel;
        assert.equal(panel.kind === "receipt" ? panel.receiptId : null, expectedIds[index]);
        assert.equal(page.next()?.disabled, index === 27);
        assert.equal(page.previous()?.disabled, index === 0);
      };
      const jumpTo = async (index: number) => {
        await page.act(async () => page.api().openPanel({ ...origin, receiptId: expectedIds[index] }));
        await expectPosition(index);
      };

      // Render the same controls at the start, middle and end in every variant.
      await expectPosition(0);
      for (const index of [1, 2]) {
        await page.click(page.next());
        await expectPosition(index);
      }
      await jumpTo(13);
      await page.click(page.next());
      await expectPosition(14);
      await jumpTo(26);
      await page.click(page.next());
      await expectPosition(27);
      await page.click(page.previous());
      await expectPosition(26);
    } finally { await page.cleanup(); }
  });
}
