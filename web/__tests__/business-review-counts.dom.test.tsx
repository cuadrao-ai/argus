import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptActivityCounts } from "@/lib/business-api";

// The real workspace provider over the sample source, with the Resumen, the
// sidebar badge and the Bandeja side by side on the same saved state. The
// sample lists five receipts (Ferretería La Esquina, Papelería Central,
// IMG_2209, IMG_2215, colmado-oct) and five emails; three of the receipts
// need attention and IMG_2209 is unreadable, so four are to review. Two emails
// brought no receipt (problems) and one is still being read.
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
  const rows = () => host.querySelectorAll('[data-testid="bandeja-row"], [data-testid="bandeja-note"]').length;
  const segment = (key: "review" | "problem" | "all") => host.querySelector<HTMLButtonElement>(`[data-testid="bandeja-segments"] [data-segment="${key}"]`);
  const choose = (key: "review" | "problem" | "all") => act(async () => segment(key)!.click());
  await settle(() => rows() > 0 && api?.records.notes !== null && api?.records.overview !== null && reviewCount() !== null);
  return { act, root, host, settle, text, rows, segment, choose, reviewCount, reviewTask, api: () => api!, source };
}

describe("the Bandeja and the Resumen on one saved state", () => {
  test("the Resumen card, the sidebar badge and the Por revisar segment agree; attention is its own count", async () => {
    const page = await mount();
    assert.equal(page.rows(), 4, "Por revisar lists the four receipts to review");
    assert.equal(page.reviewCount(), "4");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "4");
    assert.equal(page.segment("review")?.textContent, "Por revisar4");
    await page.choose("all");
    assert.equal(page.rows(), 5, "Todo lists five receipts; the email itself is not a row");
    assert.equal(page.host.querySelector('[data-testid="inicio-por-revisar"]'), null, "the old card is gone");
    assert.equal(page.host.querySelector('[data-testid="overview-inbox-count"]'), null);
    assert.equal(page.host.querySelector('[data-testid="overview-real-expenses"]'), null);
    assert.equal(page.host.textContent?.includes("necesita tu atención"), false);
    assert.equal(/Revisar \d+ recibos/.test(page.host.textContent ?? ""), false);
    assert.equal(page.host.textContent?.includes("DOP"), false);
    assert.match(page.text('[data-testid="business-inbox-receipts"]') ?? "", /RD\$/);
    await page.act(async () => page.root.unmount());
  });

  test("a saved note is a Por revisar row and the segment counts it", async () => {
    const page = await mount();
    await page.act(async () => {
      await page.source.captureNote({ text: "Pagué 850 en la ferretería" }, "note-1113");
      page.api().reload();
    });
    // The note row comes from the notes list, the number from the server's next count.
    await page.settle(() => page.host.querySelectorAll('[data-testid="bandeja-note"]').length === 1 && page.segment("review")?.textContent === "Por revisar5");
    assert.equal(page.host.querySelectorAll('[data-testid="bandeja-note"]').length, 1);
    assert.equal(page.rows(), 5);
    assert.equal(page.segment("review")?.textContent, "Por revisar5");
    await page.act(async () => page.root.unmount());
  });

  test("a saved note counts alike on the Resumen, the badge and the Por revisar segment", async () => {
    const page = await mount();
    await page.act(async () => {
      await page.source.captureNote({ text: "Pagué 850 en la ferretería" }, "note-1113");
      page.api().reload();
    });
    // The note row comes from the notes list, the number from the server's next count.
    await page.settle(() => page.host.querySelectorAll('[data-testid="bandeja-note"]').length === 1 && page.segment("review")?.textContent === "Por revisar5");
    assert.equal(page.segment("review")?.textContent, "Por revisar5");
    assert.equal(page.reviewCount(), "5");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), "5");
    await page.act(async () => page.root.unmount());
  });

  test("the Con problema segment counts the receipts with a problem and the emails that brought none, and lists what it counts", async () => {
    const page = await mount();
    const { problemCount } = await import("@/components/business-app/inbox-count");
    await page.settle(() => page.segment("problem")?.textContent === "Con problema5");
    assert.equal(page.segment("problem")?.textContent, "Con problema5");
    assert.equal(problemCount(page.api().records), 5, "the one owner gives the same number");
    await page.choose("problem");
    assert.equal(page.rows() + page.host.querySelectorAll('[data-testid="bandeja-email"]').length, 5, "the segment lists the five it counts");
    await page.act(async () => page.root.unmount());
  });

  // Fails until Inicio reads problemCount and readingCount from inbox-count (BusinessOverviewPanel.tsx is held by another helper).
  test("the Resumen's con problema and the Con problema segment give one number", async () => {
    const page = await mount();
    await page.settle(() => page.segment("problem")?.textContent === "Con problema5");
    try {
      assert.match(page.reviewTask()?.textContent ?? "", /5 con problema/);
      assert.match(page.reviewTask()?.textContent ?? "", /1 todavía leyendo/);
    } finally { await page.act(async () => page.root.unmount()); }
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
    assert.equal(page.segment("review")?.textContent, "Por revisar3");
    assert.equal(page.rows(), 3);
    await page.act(async () => page.api().reload());
    await page.settle(() => false);
    assert.equal(page.reviewCount(), "3");
    await page.act(async () => page.root.unmount());
  });

  test("a desktop Inicio and Bandeja repeat no top-bar action, and the accountant's Bandeja keeps one Revisar recibos", async () => {
    const owner = await mount();
    for (const id of ["resumen", "bandeja"]) {
      const screen = owner.host.querySelector(`[data-testid="${id}"]`)!;
      assert.equal(screen.querySelectorAll('[data-primary="true"]').length, 0, `${id} has no primary of its own`);
      for (const gone of ["inicio-actions", "inicio-export", "inicio-forward-copy", "inicio-primary-review", "add-menu-page", "business-primary-upload"]) {
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
    assert.notEqual(page.reviewCount(), "4");
    assert.equal(page.text('[data-testid="business-inbox-count"]'), null);
    assert.equal(page.segment("review")?.textContent, "Por revisar-");
    await page.act(async () => page.root.unmount());
  });
});
