import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptDetail } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

// The real workspace and panel router over the sample source: every state of
// a receipt opens the same review page (source on the left, fields and their
// one action on the right), the Personal mark goes on and comes off through
// its action, and a saved edit is still there after a trip to the Bandeja.
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

async function mount(overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource> = () => ({})) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  // The email's own document stands in for a receipt saved with reading off.
  const source = {
    ...fixture,
    receipt: async (id: string, signal?: AbortSignal): Promise<ReceiptDetail> => {
      const found = await fixture.receipt(id, signal);
      return id === "rcpt-saved" ? { ...found, email_original: false, activity: { state: "saved_unread", unread: true, completion_cursor: null } } : found;
    },
    ...overrides(fixture),
  };
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
        <BusinessWorkspaceProvider source={source as never}>
          <Probe />
        </BusinessWorkspaceProvider>
      </I18nextProvider>,
    );
  });
  const wait = async (done: () => boolean) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out: ${host.textContent?.slice(0, 300)}`);
  };
  const open = async (panel: Parameters<ReturnType<typeof useBusiness>["openPanel"]>[0], ready: () => boolean) => {
    await act(async () => api!.openPanel(panel));
    await wait(ready);
  };
  const pages = () => host.querySelectorAll('[data-testid="business-record-review"]');
  const frame = () => {
    const [page] = pages();
    return {
      count: pages().length,
      source: page?.querySelector('[data-testid="receipt-review-source"]') ?? null,
      fields: page?.querySelector('[data-testid="receipt-review-fields"]') ?? null,
      title: page?.querySelector("#receipt-review-title")?.textContent ?? null,
    };
  };
  return { act, root, host, wait, open, frame, source, api: () => api! };
}

describe("one receipt review page", () => {
  test("prepared and unread receipts show the saved English default in Spanish", async () => {
    const page = await mount((fixture) => ({
      dossier: async (id) => ({ ...await fixture.dossier(id), space_name: "My business" }),
      receipt: async (id, signal) => {
        const found = await fixture.receipt(id, signal);
        assert.ok(found.record_context);
        return { ...found, email_original: false, record_context: { ...found.record_context, space_name: "My business" } };
      },
    }));
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    for (const panel of [
      { kind: "draft", draftId: dossierFixtureIds.ready },
      { kind: "receipt", receiptId: "rcpt-saved" },
    ] as const) {
      await page.open(panel, () => page.frame().fields !== null);
      const review = page.host.querySelector('[data-testid="business-record-review"]');
      assert.ok(review?.querySelector("header")?.textContent?.includes("Mi negocio"));
      assert.ok(!review?.textContent?.includes("My business"));
      await page.open({ kind: "inbox" }, () => page.frame().count === 0);
    }
    await page.act(async () => page.root.unmount());
  });

  test("a read receipt, a failed read and a receipt saved unread all open the same page", async () => {
    const page = await mount();
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    for (const [panel, title] of [
      [{ kind: "draft", draftId: dossierFixtureIds.ready }, null],
      [{ kind: "receipt", receiptId: "rcpt-blurry" }, "Revisar recibo"],
      [{ kind: "receipt", receiptId: "rcpt-saved" }, "Revisar recibo"],
    ] as const) {
      await page.open(panel, () => page.frame().fields !== null && page.frame().source?.textContent !== "");
      const shown = page.frame();
      assert.equal(shown.count, 1, `one page for ${JSON.stringify(panel)}`);
      assert.ok(shown.source && shown.fields && shown.title, "source on the left, fields on the right, one title");
      if (title) assert.equal(shown.title, title);
      await page.open({ kind: "inbox" }, () => page.frame().count === 0);
    }
    await page.act(async () => page.root.unmount());
  });

  test("a prepared record has one Aprobar, and a saved edit and its revision survive a trip to the Bandeja", async () => {
    const page = await mount();
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const id = dossierFixtureIds.ready;
    await page.open({ kind: "draft", draftId: id }, () => page.frame().fields !== null);
    const approve = [...page.host.querySelectorAll('[data-testid="receipt-review-footer"] button')].filter((button) => button.textContent === "Aprobar");
    assert.equal(approve.length, 1);
    const before = await page.source.dossier(id);
    await page.act(async () => {
      await page.source.reviewDraft(id, before.version, { counterparty: { state: "known", value: "Ferretería Prueba Revisada" } }, "edit-1113");
    });
    await page.open({ kind: "inbox" }, () => page.frame().count === 0);
    await page.open({ kind: "draft", draftId: id }, () => page.frame().title === "Ferretería Prueba Revisada");
    assert.match(page.host.querySelector('[data-testid="business-record-review"] header')?.textContent ?? "", /Revisión \d+/);
    const after = await page.source.dossier(id);
    assert.equal(after.version, before.version + 1);
    // Saving review details never approves: the record is still awaiting review.
    assert.equal(after.review_state, "open");
    assert.equal(after.approval_result, null);
    await page.act(async () => page.root.unmount());
  });

  test("the Personal mark goes on and comes off from the review page", async () => {
    const page = await mount();
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    await page.open({ kind: "draft", draftId: dossierFixtureIds.ready }, () => page.host.querySelector('[data-testid="receipt-mark-personal"]') !== null);
    const toggle = () => page.host.querySelector('[data-testid="receipt-mark-personal"]') as HTMLButtonElement;
    assert.equal(toggle().getAttribute("aria-pressed"), "false");
    await page.act(async () => toggle().click());
    await page.wait(() => toggle().getAttribute("aria-pressed") === "true");
    assert.equal(toggle().textContent, "Ya no es personal");
    await page.act(async () => toggle().click());
    await page.wait(() => toggle().getAttribute("aria-pressed") === "false");
    assert.equal(toggle().textContent, "Marcar como personal");
    await page.act(async () => page.root.unmount());
  });
});
