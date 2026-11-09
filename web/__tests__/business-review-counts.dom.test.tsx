import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { receptionRows, receptionTab } from "./support/reception";
import type { ReceiptActivityCounts } from "@/lib/business-api";

// The real workspace provider over the sample source, with the Resumen, the
// sidebar badge and the Bandeja side by side on the same saved state.
const SAMPLE = { listos: 5, attention: 12, total: 19, problems: 5, reading: 2 };
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

async function mount(overrides: { activity?: (counts: ReceiptActivityCounts) => ReceiptActivityCounts | null; grant?: string | null; bars?: boolean } = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessOverviewPanel = (await import("@/components/business-app/BusinessOverviewPanel")).default;
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const BusinessHeader = (await import("@/components/business-app/foundation/BusinessHeader")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(overrides.grant ?? null);
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
        {overrides.bars ? <div data-testid="bar-resumen"><BusinessHeader home name={null} screen="overview" /></div> : null}
        <div data-testid="resumen"><BusinessOverviewPanel /></div>
        {overrides.bars ? <div data-testid="bar-bandeja"><BusinessHeader home={false} name={null} screen="inbox" /></div> : null}
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
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 60; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
  };
  const updateButton = () => [...host.querySelectorAll("button")].find((button) => button.textContent === "Actualizar lista") ?? null;
  const noteRows = () => receptionRows(host).filter((row) => row.dataset.kind === "note").length;
  const text = (selector: string) => host.querySelector(selector)?.textContent ?? null;
  // Inicio's Necesita atención counts everything waiting in the Bandeja, the sidebar's one server count.
  const reviewCount = () => host.querySelector('[data-testid="resumen"] [data-testid="home-attention-count"]')?.textContent ?? null;
  const rows = () => receptionRows(host).length;
  const segment = (key: "attention" | "listos" | "all") => receptionTab(host, key);
  const choose = (key: "attention" | "listos" | "all") => act(async () => segment(key)!.click());
  await settle(() => rows() > 0 && api?.records.notes !== null && api?.records.overview !== null && host.querySelector('[data-testid="home-month-body"][data-state="ready"]') !== null);
  await settle(() => reviewCount() !== null);
  return { act, root, host, settle, text, rows, noteRows, updateButton, segment, choose, reviewCount, api: () => api!, source };
}

describe("the Bandeja and the Resumen on one saved state", () => {
  test("the Resumen, the sidebar badge and the two tabs read one server pair, and each tab lists what it counts", async () => {
    const page = await mount();
    assert.equal(page.reviewCount(), String(SAMPLE.total));
    assert.equal(page.text('[data-testid="business-inbox-count"]'), String(SAMPLE.total));
    await page.settle(() => page.segment("attention")?.textContent === `Necesitan atención${SAMPLE.attention}`);
    assert.equal(page.segment("listos")?.textContent, `Listos${SAMPLE.listos}`);
    assert.equal(page.segment("all")?.textContent, "Todos", "Todos has no count");
    await page.choose("attention");
    assert.equal(page.rows(), SAMPLE.attention);
    await page.choose("listos");
    assert.equal(page.rows(), SAMPLE.listos);
    await page.choose("all");
    assert.equal(page.host.querySelector('[data-testid="inicio-por-revisar"]'), null, "the old card is gone");
    assert.equal(page.host.querySelector('[data-testid="overview-inbox-count"]'), null);
    assert.equal(page.host.querySelector('[data-testid="overview-real-expenses"]'), null);
    assert.equal(page.host.textContent?.includes("necesita tu atención"), false);
    assert.equal(/Revisar \d+ recibos/.test(page.host.textContent ?? ""), false);
    assert.equal(page.host.textContent?.includes("DOP"), false);
    await page.act(async () => page.root.unmount());
  });

  test("a saved note needs attention and counts alike on the Resumen, the badge and the tab", async () => {
    const page = await mount();
    await page.act(async () => {
      await page.source.captureNote({ text: "Pagué 850 en la ferretería" }, "note-1113");
      page.api().reload();
    });
    // The note row comes from the notes list, the number from the server's next count.
    await page.settle(() => page.segment("attention")?.textContent === `Necesitan atención${SAMPLE.attention + 1}` && page.updateButton() !== null);
    assert.equal(page.reviewCount(), String(SAMPLE.total + 1));
    assert.equal(page.text('[data-testid="business-inbox-count"]'), String(SAMPLE.total + 1));
    await page.act(async () => page.updateButton()!.click());
    await page.choose("attention");
    assert.equal(page.noteRows(), 2, "the sample's own note and this one");
    assert.equal(page.rows(), SAMPLE.attention + 1);
    await page.act(async () => page.root.unmount());
  });

  test("an approval leaves the Bandeja and the Resumen together", async () => {
    const page = await mount();
    assert.equal(page.reviewCount(), String(SAMPLE.total));
    await page.act(async () => {
      const receipt = await page.source.receipt("rcpt-ferreteria");
      const saved = await page.source.saveReview(receipt.id, receipt.version, { account_id: "acct-ops" });
      const record = await page.source.dossier(saved.draft_id!);
      await page.source.approveDraft(record.draft_id, record.version, "approve-1113", "record_expense");
      page.api().reload();
    });
    const left = String(SAMPLE.total - 1);
    await page.settle(() => page.reviewCount() === left);
    assert.equal(page.reviewCount(), left);
    assert.equal(page.text('[data-testid="business-inbox-count"]'), left);
    assert.equal(page.segment("attention")?.textContent, `Necesitan atención${SAMPLE.attention - 1}`);
    await page.choose("attention");
    assert.equal(page.rows(), SAMPLE.attention - 1);
    await page.act(async () => page.api().reload());
    await page.settle(() => false);
    assert.equal(page.reviewCount(), left);
    await page.act(async () => page.root.unmount());
  });

  test("desktop Inicio and Bandeja each offer one Agregar, in the top bar, and the accountant's Bandeja keeps one Revisar recibos", async () => {
    const owner = await mount({ bars: true });
    for (const id of ["resumen", "bandeja"]) {
      const bar = owner.host.querySelector(`[data-testid="bar-${id}"] [data-testid="business-bar-tools"]`)!;
      assert.equal(bar.querySelectorAll('[data-testid="add-menu-header"]').length, 1, `${id}'s bar has one Agregar`);
      assert.equal(bar.querySelectorAll('[data-testid="business-primary-upload"]').length, 1);
      const screen = owner.host.querySelector(`[data-testid="${id}"]`)!;
      assert.equal(screen.querySelectorAll('[data-primary="true"]').length, 0, `${id} leaves its primary to the bar`);
      for (const gone of ["business-primary-upload", "inicio-actions", "inicio-export", "inicio-forward-copy", "inicio-primary-review", "add-menu-page", "add-menu-header"]) {
        assert.equal(screen.querySelector(`[data-testid="${gone}"]`), null, `${id} has no ${gone}`);
      }
    }
    await owner.act(async () => owner.root.unmount());

    const accountant = await mount({ grant: "fixture-grant-client" });
    const resumen = accountant.host.querySelector('[data-testid="resumen"]')!;
    assert.equal(resumen.querySelector('[data-testid="inicio-primary-review"]'), null);
    const review = accountant.host.querySelectorAll('[data-testid="bandeja"] [data-testid="business-primary-review"]');
    assert.equal(review.length, 1);
    assert.equal(review[0]?.textContent, "Revisar recibos");
    assert.equal(accountant.host.querySelector('[data-testid="business-primary-upload"]'), null);
    await accountant.act(async () => accountant.root.unmount());
  });

  test("a missing activity object does not invent a zero, nor a count of the rows that loaded", async () => {
    const page = await mount({ activity: () => null });
    assert.notEqual(page.reviewCount(), "0");
    assert.notEqual(page.reviewCount(), String(SAMPLE.total));
    assert.equal(page.text('[data-testid="business-inbox-count"]'), null);
    assert.equal(page.segment("attention")?.textContent, "Necesitan atención-");
    assert.equal(page.segment("listos")?.textContent, "Listos-");
    await page.act(async () => page.root.unmount());
  });
});
