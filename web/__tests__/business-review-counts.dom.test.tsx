import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptActivityCounts } from "@/lib/business-api";

// The real workspace provider over the sample source, with the Resumen, the
// sidebar badge and the Bandeja side by side on the same saved state. The
// sample lists five receipts awaiting review (Ferretería La Esquina,
// Papelería Central, IMG_2209, IMG_2215, colmado-oct) and one email that is
// context for its attachment; three of the five need attention and none is
// unread. Before the fix, the Resumen and the badge showed the unread count
// (absent here, so 0) while the Bandeja listed five rows.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount(overrides: { activity?: (counts: ReceiptActivityCounts) => ReceiptActivityCounts | null } = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const source = {
    ...fixture,
    receiptPage: async (view: "inbox" | "all") => {
      const page = await fixture.receiptPage!(view);
      return { ...page, activity: overrides.activity ? overrides.activity(page.activity) : page.activity } as Awaited<ReturnType<NonNullable<typeof fixture.receiptPage>>>;
    },
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  const shell = { currentView: "workspace" as const, conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Probe() {
    api = useBusiness();
    return (
      <div>
        <div data-testid="sidebar"><BusinessSidebarNav shell={shell} /></div>
        <div data-testid="resumen"><BusinessOverviewPanel /></div>
        <div data-testid="bandeja"><BusinessInboxPanel /></div>
      </div>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessWorkspaceProvider source={source as never}>
          <Probe />
        </BusinessWorkspaceProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 60; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
  };
  const text = (selector: string) => host.querySelector(selector)?.textContent ?? null;
  const rows = () => host.querySelectorAll('[data-testid="business-inbox-receipts"] > li, [data-testid="business-inbox-notes"] > li').length;
  await settle(() => rows() > 0 && api?.records.notes !== null && api?.records.overview !== null);
  return { act, root, host, settle, text, rows, api: () => api!, source };
}

describe("the Bandeja and the Resumen on one saved state", () => {
  test("the Resumen card, the sidebar badge and the Bandeja rows agree; attention is its own count", async () => {
    const page = await mount();
    assert.equal(page.rows(), 5, "five receipts listed; the email itself is not a row");
    assert.equal(page.text('[data-testid="overview-inbox-count"]'), "5");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "5");
    assert.match(page.text('[data-testid="overview-attention"]') ?? "", /3 con problema/);
    // The starter chip under the Resumen names the same number.
    assert.ok([...page.host.querySelectorAll('[data-testid="resumen"] button')].some((button) => button.textContent === "Revisar 5 recibos"));
    await page.act(async () => page.root.unmount());
  });

  test("a saved note joins the count once, after the same reload that lists it", async () => {
    const page = await mount();
    await page.act(async () => {
      await page.source.captureNote({ text: "Pagué 850 en la ferretería" }, "note-1113");
      page.api().reload();
    });
    await page.settle(() => page.text('[data-testid="overview-inbox-count"]') === "6");
    assert.equal(page.host.querySelectorAll('[data-testid="business-inbox-notes"] li').length, 1);
    assert.equal(page.rows(), 6);
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "6");
    await page.act(async () => page.root.unmount());
  });

  test("an approval leaves the Bandeja and the Resumen together, and Gastos reales counts it once", async () => {
    const page = await mount();
    const real = () => [...page.host.querySelectorAll('[data-testid="overview-real-expenses"] li')].map((item) => item.textContent).sort();
    assert.deepEqual(real(), ["RD$ 2,100.001 gasto", "US$ 24.001 gasto"]);
    await page.act(async () => {
      const receipt = await page.source.receipt("rcpt-ferreteria");
      const saved = await page.source.saveReview(receipt.id, receipt.version, { account_id: "acct-ops" });
      const record = await page.source.dossier(saved.draft_id!);
      await page.source.approveDraft(record.draft_id, record.version, "approve-1113");
      page.api().reload();
    });
    await page.settle(() => page.text('[data-testid="overview-inbox-count"]') === "4");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "4");
    assert.equal(page.rows(), 4);
    assert.deepEqual(real(), ["RD$ 5,550.002 gastos", "US$ 24.001 gasto"]);
    // A second reload reads the same saved state: nothing stale, nothing doubled.
    await page.act(async () => page.api().reload());
    await page.settle(() => false);
    assert.equal(page.text('[data-testid="overview-inbox-count"]'), "4");
    assert.deepEqual(real(), ["RD$ 5,550.002 gastos", "US$ 24.001 gasto"]);
    await page.act(async () => page.root.unmount());
  });

  test("an unknown count is never shown as 0", async () => {
    const page = await mount({ activity: () => null });
    assert.equal(page.host.querySelector('[data-testid="overview-inbox-count"]'), null);
    assert.equal(page.host.querySelector('[data-testid="business-inbox-count"]'), null);
    assert.equal(page.host.querySelector('[data-testid="overview-attention"]'), null);
    assert.ok(page.host.querySelector('[data-testid="overview-inbox"]'), "the card stays, without a number");
    await page.act(async () => page.root.unmount());
  });
});
