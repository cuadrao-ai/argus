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

async function mount(overrides: { activity?: (counts: ReceiptActivityCounts) => ReceiptActivityCounts | null; grant?: string | null } = {}) {
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
  const text = (selector: string) => host.querySelector(selector)?.textContent ?? null;
  // The Resumen's number is the first line of the month checklist: "Revisa N recibos en la Bandeja".
  const reviewTask = () => host.querySelector('[data-testid="resumen"] [data-testid="month-close-task-review"]');
  const reviewCount = () => reviewTask()?.querySelector("p")?.textContent?.match(/^Revisa (\d+) recibos?/)?.[1] ?? null;
  const rows = () => host.querySelectorAll('[data-testid="business-inbox-receipts"] > li, [data-testid="business-inbox-notes"] > li').length;
  await settle(() => rows() > 0 && api?.records.notes !== null && api?.records.overview !== null && reviewCount() !== null);
  return { act, root, host, settle, text, rows, reviewCount, reviewTask, api: () => api!, source };
}

describe("the Bandeja and the Resumen on one saved state", () => {
  test("the Resumen card, the sidebar badge and the Bandeja rows agree; attention is its own count", async () => {
    const page = await mount();
    assert.equal(page.rows(), 5, "five receipts listed; the email itself is not a row");
    assert.equal(page.reviewCount(), "4");
    assert.match(page.reviewTask()?.textContent ?? "", /1 con problema/);
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "4");
    assert.equal(page.text('[data-testid="bandeja-por-revisar"]'), "4 por revisar");
    assert.equal(page.text('[data-testid="bandeja-aside"]'), "1 no se pudo leer.");
    assert.equal(page.host.querySelector('[data-testid="inicio-por-revisar"]'), null, "the old card is gone");
    assert.equal(page.host.querySelector('[data-testid="overview-inbox-count"]'), null);
    assert.equal(page.host.querySelector('[data-testid="overview-real-expenses"]'), null);
    assert.equal(page.host.textContent?.includes("necesita tu atención"), false);
    assert.equal(/Revisar \d+ recibos/.test(page.host.textContent ?? ""), false);
    assert.equal(page.host.textContent?.includes("DOP"), false);
    assert.match(page.text('[data-testid="business-inbox-receipts"]') ?? "", /RD\$/);
    await page.act(async () => page.root.unmount());
  });

  test("a saved note is listed and stays out of the por revisar number", async () => {
    const page = await mount();
    await page.act(async () => {
      await page.source.captureNote({ text: "Pagué 850 en la ferretería" }, "note-1113");
      page.api().reload();
    });
    await page.settle(() => page.host.querySelectorAll('[data-testid="business-inbox-notes"] li').length === 1);
    assert.equal(page.host.querySelectorAll('[data-testid="business-inbox-notes"] li').length, 1);
    assert.equal(page.rows(), 6);
    assert.equal(page.reviewCount(), "4");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "4");
    await page.act(async () => page.root.unmount());
  });

  test("an approval leaves the Bandeja and the Resumen together", async () => {
    const page = await mount();
    assert.equal(page.reviewCount(), "4");
    await page.act(async () => {
      const receipt = await page.source.receipt("rcpt-ferreteria");
      const saved = await page.source.saveReview(receipt.id, receipt.version, { account_id: "acct-ops" });
      const record = await page.source.dossier(saved.draft_id!);
      await page.source.approveDraft(record.draft_id, record.version, "approve-1113");
      page.api().reload();
    });
    await page.settle(() => page.reviewCount() === "3");
    assert.equal(page.reviewCount(), "3");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "3");
    assert.equal(page.rows(), 4);
    await page.act(async () => page.api().reload());
    await page.settle(() => false);
    assert.equal(page.reviewCount(), "3");
    await page.act(async () => page.root.unmount());
  });

  test("the owner gets one upload primary and the accountant gets one review primary", async () => {
    const owner = await mount();
    const resumen = owner.host.querySelector('[data-testid="resumen"]')!;
    const primaries = resumen.querySelectorAll('[data-primary="true"]');
    assert.equal(primaries.length, 1);
    assert.equal(primaries[0]?.getAttribute("data-testid"), "business-primary-upload");
    assert.equal(primaries[0]?.textContent, "Subir recibo");
    assert.match(primaries[0]?.className ?? "", /min-h-11/);
    const actions = resumen.querySelector('[data-testid="inicio-actions"]');
    const cards = resumen.querySelector('[data-testid="month-close-cards"]');
    assert.ok(actions && cards && (actions.compareDocumentPosition(cards) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0, "the action row comes before the month figures");
    assert.ok(actions.contains(primaries[0]!));
    for (const id of ["inicio-record-expense", "inicio-export"]) assert.ok(actions.querySelector(`[data-testid="${id}"]`), id);
    await owner.settle(() => resumen.querySelector('[data-testid="inicio-forward-copy"]') !== null);
    const copy = resumen.querySelector('[data-testid="inicio-forward-copy"]') as HTMLButtonElement | null;
    assert.ok(copy && actions.contains(copy), "the forwarding address copies from the action row");
    assert.match(copy.className, /min-h-11/);
    const copied: string[] = [];
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: async (value: string) => { copied.push(value); } } });
    await owner.act(async () => { copy.click(); });
    assert.equal(copied.length, 1);
    assert.match(copied[0]!, /@/);
    await owner.act(async () => owner.root.unmount());

    const accountant = await mount({ grant: "fixture-grant-client" });
    const view = accountant.host.querySelector('[data-testid="resumen"]')!;
    const review = view.querySelectorAll('[data-primary="true"]');
    assert.equal(review.length, 1);
    assert.equal(review[0]?.getAttribute("data-testid"), "inicio-primary-review");
    assert.equal(review[0]?.textContent, "Revisar recibos");
    assert.equal(view.querySelector('[data-testid="business-primary-upload"]'), null);
    await accountant.act(async () => accountant.root.unmount());
  });

  test("a missing activity object does not invent a zero", async () => {
    const page = await mount({ activity: () => null });
    assert.equal(page.reviewCount(), "4");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "4");
    assert.equal(page.text('[data-testid="bandeja-por-revisar"]'), "4 por revisar");
    assert.equal(page.host.textContent?.includes("0 por revisar"), false);
    await page.act(async () => page.root.unmount());
  });
});
