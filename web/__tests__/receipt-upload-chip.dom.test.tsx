import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { ReceiptDetail, ReceiptSummary } from "@/lib/business-api";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

type Attempt = { name: string; key: string; finish: (receipt: ReceiptSummary) => void; fail: (error: unknown) => void };

/** The mounted Business workspace with its real queue, top bar and upload panel; every upload is held for the test to end. */
async function workspace(withBandeja = false) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  setChosenGrant(null);
  const base = createFixtureBusinessDataSource({ chatAvailable: false });
  const template = await base.receipt("rcpt-ferreteria");
  const older = await base.receipt("rcpt-blurry");
  const arrivals: ReceiptDetail[] = ["receipt-older", "receipt-b", "receipt-a"].map((id, index) => ({
    ...older,
    id,
    merchant: id,
    activity: { state: "ready", unread: false, completion_cursor: null },
    received_at: new Date(Date.UTC(2026, 9, 28, 12, 0, -index)).toISOString(),
  }));
  const activity = (await base.receiptPage!("all")).activity;
  const attempts: Attempt[] = [];
  const source = {
    ...base,
    ...(withBandeja ? {
      receipts: async () => arrivals,
      receiptPage: async () => ({ items: arrivals, activity }),
      emailDeliveries: async () => [],
      captures: async () => ({ items: [] }),
      receipt: async (id: string) => {
        const receipt = arrivals.find((item) => item.id === id);
        assert.ok(receipt);
        return receipt;
      },
    } : {}),
    uploadReceipt: (file: File, _consent: boolean, key: string) => new Promise<ReceiptSummary>((resolve, reject) => { attempts.push({ name: file.name, key, finish: resolve, fail: reject }); }),
  } satisfies Partial<BusinessDataSource>;
  const state: { panel: unknown; business?: ReturnType<typeof useBusiness> } = { panel: null };
  function TopBar() {
    const chat = useChatWorkspace();
    const business = useBusiness();
    state.panel = business.panel;
    state.business = business;
    return <>
      <header>{chat?.headerActions?.({ currentView: "workspace", conversationId: null, isBelowTablet: false, sidebarCollapsed: false } as never)}</header>
      <button type="button" data-testid="open-agregar" onClick={() => business.actions.create.find((action) => action.id === "upload_receipt")?.run()}>+</button>
      {withBandeja ? <BusinessPanel /> : null}
    </>;
  }
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source as never}><TopBar /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>));
  const turn = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)); });
  const until = async (ready: () => boolean, what: string) => { for (let i = 0; i < 200 && !ready(); i += 1) await turn(); assert.ok(ready(), what); };
  const click = (node: HTMLElement | null | undefined) => { assert.ok(node, "the control is on the page"); return act(async () => node.click()); };
  const chip = () => document.querySelector<HTMLButtonElement>('[data-testid="receipt-upload-chip"]');
  const dialog = () => [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].find((node) => node.textContent?.includes("Agregar documentos"));
  const rows = () => [...host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')].map((row) => row.dataset.listRow);
  if (withBandeja) {
    await act(async () => state.business!.openPanel({ kind: "inbox" }));
    await until(() => state.business?.chosen != null && rows().length === arrivals.length, "Bandeja rows are mounted");
  }
  await click(document.querySelector<HTMLElement>('[data-testid="open-agregar"]'));
  await until(() => Boolean(dialog()?.querySelector('input[type="file"]')), "Agregar is open with its picker");
  return {
    act, attempts, state, turn, until, click, chip, dialog, rows,
    receipt: (id: string): ReceiptSummary => ({ ...template, id }),
    choose: (...names: string[]) => act(async () => {
      const input = dialog()!.querySelector<HTMLInputElement>('input[type="file"]:not([capture])')!;
      const transfer = new DataTransfer();
      for (const name of names) transfer.items.add(new File(["recibo"], name, { type: "image/jpeg" }));
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }),
    /** Whether leaving the page now would ask first, the way the browser asks on refresh. */
    leavingAsks: () => !window.dispatchEvent(new Event("beforeunload", { cancelable: true })),
    close: () => click([...dialog()!.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.getAttribute("aria-label") === "Cerrar")),
    unmount: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

test("closing the panel keeps the uploads going behind a chip, leaving asks first, the connection coming back retries by itself, and review opens the batch", async () => {
  const page = await workspace();
  assert.equal(page.chip(), null, "no chip with nothing uploaded");
  assert.equal(page.leavingAsks(), false);
  await page.choose("a.jpg", "b.jpg");
  assert.equal(page.chip(), null, "the open panel is the status");
  await page.close();
  assert.equal(page.dialog(), undefined);
  assert.equal(page.chip()?.textContent, "Subiendo 1 de 2");
  assert.equal(page.chip()?.dataset.busy, "true");
  assert.equal(page.leavingAsks(), true, "leaving would lose the files still to send");

  await page.act(async () => page.attempts[0].finish(page.receipt("receipt-a")));
  await page.until(() => page.attempts.length === 2, "closing did not stop the next file");
  assert.equal(page.chip()?.textContent, "Subiendo 2 de 2");
  await page.act(async () => page.attempts[1].fail(new TypeError("Failed to fetch")));
  await page.until(() => page.chip()?.dataset.busy === "false", "the batch stopped");
  assert.equal(page.chip()?.textContent, "1 subido · 1 sin subir");
  assert.equal(page.leavingAsks(), true, "a stopped file is still to send");

  await page.act(async () => { window.dispatchEvent(new Event("online")); });
  await page.until(() => page.attempts.length === 3, "the browser coming back online sends the stopped file again");
  assert.equal(page.attempts[2].name, "b.jpg");
  assert.equal(page.attempts[2].key, page.attempts[1].key, "with the same upload key, so it is never saved twice");
  assert.equal(page.chip()?.textContent, "Subiendo 1 de 1");
  await page.act(async () => page.attempts[2].finish(page.receipt("receipt-b")));
  await page.until(() => page.chip()?.textContent === "2 subidos", "both are saved");
  assert.equal(page.leavingAsks(), false, "saved files need nothing from this page");

  await page.click(page.chip());
  await page.until(() => Boolean(page.dialog()), "the chip opens the panel again");
  assert.equal(page.chip(), null);
  assert.match(page.dialog()?.textContent ?? "", /2 guardados/);
  await page.click(page.dialog()!.querySelector<HTMLButtonElement>('[data-testid="receipt-intake-review"]'));
  assert.deepEqual(page.state.panel, { kind: "receipt", receiptId: "receipt-a", list: "inbox", reviewList: { scope: "batch", receiptIds: ["receipt-a", "receipt-b"] } }, "the dossier opens on 1 of this batch");
  assert.equal(page.dialog(), undefined);
  assert.equal(page.chip(), null, "the reviewed list is cleared");
  await page.unmount();
});

test("the same bytes under two names count once in the chip, and the dossier walks each document once", async () => {
  const page = await workspace();
  await page.choose("a.jpg", "a-copia.jpg", "b.jpg");
  await page.close();
  for (const [index, id] of ["receipt-a", "receipt-a", "receipt-b"].entries()) {
    await page.until(() => page.attempts.length === index + 1, "the next file is sent");
    await page.act(async () => page.attempts[index].finish({ ...page.receipt(id), ...(index === 1 ? { replayed: true } : {}) }));
  }
  await page.until(() => page.chip()?.dataset.busy === "false", "the batch ended");
  assert.equal(page.chip()?.textContent, "2 subidos");
  await page.click(page.chip());
  await page.until(() => Boolean(page.dialog()), "the chip opens the panel again");
  const review = page.dialog()!.querySelector<HTMLButtonElement>('[data-testid="receipt-intake-review"]');
  assert.equal(review?.textContent, "Revisar 2 documentos");
  await page.click(review);
  assert.deepEqual(page.state.panel, { kind: "receipt", receiptId: "receipt-a", list: "inbox", reviewList: { scope: "batch", receiptIds: ["receipt-a", "receipt-b"] } });
  await page.unmount();
});

test("the upload review button walks only the saved batch while desktop Bandeja stays mounted", async () => {
  const page = await workspace(true);
  try {
    const inbox = ["receipt:receipt-older", "receipt:receipt-b", "receipt:receipt-a"];
    assert.deepEqual(page.rows(), inbox);
    await page.choose("a.jpg", "b.jpg");
    for (const [index, id] of ["receipt-a", "receipt-b"].entries()) {
      await page.until(() => page.attempts.length === index + 1, "the next file is sent");
      await page.act(async () => page.attempts[index].finish(page.receipt(id)));
    }
    const review = () => page.dialog()?.querySelector<HTMLButtonElement>('[data-testid="receipt-intake-review"]');
    await page.until(() => review()?.textContent === "Revisar 2 documentos", "the upload panel can open both saved files");
    await page.click(review());

    const position = () => document.querySelector<HTMLElement>('[data-testid="receipt-place"]');
    const heading = () => document.getElementById("receipt-review-title")?.textContent;
    const next = () => position()?.querySelector<HTMLButtonElement>('button[aria-label="Recibo siguiente"]');
    await page.until(() => heading() === "receipt-a" && position() != null, "the first uploaded receipt is open");
    assert.deepEqual(page.rows(), inbox);
    assert.equal(position()?.textContent, "1 de 2", "Bandeja order must not replace upload order");
    assert.equal(position()?.querySelector<HTMLButtonElement>('button[aria-label="Recibo anterior"]')?.disabled, true);
    await page.click(next());
    await page.until(() => heading() === "receipt-b" && position() != null, "the next uploaded receipt is open");
    assert.equal(position()?.textContent, "2 de 2");
    assert.equal(next()?.disabled, true);
  } finally {
    await page.unmount();
  }
});
