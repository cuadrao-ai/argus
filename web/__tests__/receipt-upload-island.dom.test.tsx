import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { afterAll, beforeAll, afterEach, jest, mock, test } from "bun:test";
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

const cleanups: (() => Promise<void>)[] = [];
afterEach(async () => {
  jest.useRealTimers();
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
});

type Attempt = { name: string; key: string; finish: (receipt: ReceiptSummary) => void; fail: (error: unknown) => void };

/** The mounted Business workspace with its real queue, top bar and upload panel; every upload is held for the test to end. */
async function workspace(withBandeja = false) {
  const { act, useState } = await import("react");
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
  const arrivals: ReceiptDetail[] = ["older", "b", "a"].map((name, index) => ({
    ...older,
    id: `receipt-${name}`,
    merchant: `receipt-${name}`,
    title: `${name}.jpg`,
    filename: `${name}.jpg`,
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
  const state: { panel: unknown; resize?: (phone: boolean) => void; business?: ReturnType<typeof useBusiness> } = { panel: null };
  function TopBar() {
    const [phone, resize] = useState(false);
    state.resize = resize;
    const chat = useChatWorkspace();
    const business = useBusiness();
    state.panel = business.panel;
    state.business = business;
    const shell = { currentView: "workspace", conversationId: null, isBelowTablet: phone, sidebarCollapsed: false, openSearch: () => {} } as never;
    return <>
      <header>{phone ? null : chat?.headerSearch?.(shell)}{chat?.headerActions?.(shell)}</header>
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
  const island = () => document.querySelector<HTMLButtonElement>('[data-testid="receipt-upload-island"]');
  const dialog = () => [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].find((node) => node.textContent?.includes("Agregar documentos"));
  const rows = () => [...host.querySelectorAll<HTMLElement>('[data-testid="reception-row"]')].map((row) => row.dataset.listRow);
  if (withBandeja) {
    await act(async () => state.business!.openPanel({ kind: "inbox" }));
    await until(() => state.business?.chosen != null && rows().length === arrivals.length, "Bandeja rows are mounted");
  }
  await until(() => Boolean(host.querySelector('[data-testid="business-primary-upload"]')), "Agregar is available in the header");
  await click(host.querySelector<HTMLElement>('[data-testid="business-primary-upload"]'));
  await until(() => Boolean(dialog()?.querySelector('input[type="file"]')), "Agregar is open with its picker");
  const unmount = async () => { if (host.isConnected) { await act(async () => root.unmount()); host.remove(); } };
  cleanups.push(unmount);
  return {
    act, attempts, state, turn, until, click, island, dialog, rows,
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
    unmount,
  };
}

test("closing the panel keeps the uploads going behind an island, leaving asks first, the connection coming back retries by itself, and review opens the batch", async () => {
  const page = await workspace();
  assert.equal(page.island(), null, "no island with nothing uploaded");
  assert.equal(page.leavingAsks(), false);
  await page.choose("a.jpg", "b.jpg");
  assert.equal(page.island(), null, "the open panel is the status");
  await page.close();
  assert.equal(page.dialog(), undefined);
  assert.equal(page.island()?.textContent, "1 de 2");
  assert.equal(page.island()?.dataset.state, "uploading");
  assert.equal(page.leavingAsks(), true, "leaving would lose the files still to send");

  await page.act(async () => page.attempts[0].finish(page.receipt("receipt-a")));
  await page.until(() => page.attempts.length === 2, "closing did not stop the next file");
  assert.equal(page.island()?.textContent, "2 de 2");
  await page.act(async () => page.attempts[1].fail(new TypeError("Failed to fetch")));
  await page.until(() => page.island()?.dataset.state === "failed", "the batch stopped");
  assert.equal(page.island()?.textContent, "1 sin subir");
  assert.equal(page.leavingAsks(), true, "a stopped file is still to send");

  await page.act(async () => { window.dispatchEvent(new Event("online")); });
  await page.until(() => page.attempts.length === 3, "the browser coming back online sends the stopped file again");
  assert.equal(page.attempts[2].name, "b.jpg");
  assert.equal(page.attempts[2].key, page.attempts[1].key, "with the same upload key, so it is never saved twice");
  assert.equal(page.island()?.textContent, "1 de 1");
  await page.act(async () => page.attempts[2].finish(page.receipt("receipt-b")));
  await page.until(() => page.island()?.textContent === "2 subidos", "both are saved");
  assert.equal(page.leavingAsks(), false, "saved files need nothing from this page");

  await page.click(page.island());
  await page.until(() => Boolean(page.dialog()), "the island opens the panel again");
  assert.equal(page.island(), null);
  assert.match(page.dialog()?.textContent ?? "", /2 guardados/);
  await page.click(page.dialog()!.querySelector<HTMLButtonElement>('[data-testid="receipt-intake-review"]'));
  assert.deepEqual(page.state.panel, { kind: "receipt", receiptId: "receipt-a", list: "inbox", reviewList: { scope: "batch", receiptIds: ["receipt-a", "receipt-b"] } }, "the dossier opens on 1 of this batch");
  assert.equal(page.dialog(), undefined);
  assert.equal(page.island(), null, "the reviewed list is cleared");
  await page.unmount();
});

test("the same bytes under two names count once in the island, and the dossier walks each document once", async () => {
  const page = await workspace();
  await page.choose("a.jpg", "a-copia.jpg", "b.jpg");
  await page.close();
  for (const [index, id] of ["receipt-a", "receipt-a", "receipt-b"].entries()) {
    await page.until(() => page.attempts.length === index + 1, "the next file is sent");
    await page.act(async () => page.attempts[index].finish({ ...page.receipt(id), ...(index === 1 ? { replayed: true } : {}) }));
  }
  await page.until(() => page.island()?.dataset.state === "saved", "the batch ended");
  assert.equal(page.island()?.textContent, "2 subidos");
  await page.click(page.island());
  await page.until(() => Boolean(page.dialog()), "the island opens the panel again");
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
    await page.until(() => heading() === "a.jpg" && position() != null, "the first uploaded receipt is open");
    assert.deepEqual(page.rows(), inbox);
    assert.equal(position()?.textContent, "1 de 2", "Bandeja order must not replace upload order");
    assert.equal(position()?.querySelector<HTMLButtonElement>('button[aria-label="Recibo anterior"]')?.disabled, true);
    await page.click(next());
    await page.until(() => heading() === "b.jpg" && position() != null, "the next uploaded receipt is open");
    assert.equal(position()?.textContent, "2 de 2");
    assert.equal(next()?.disabled, true);
  } finally {
    await page.unmount();
  }
});

test("the header shows 3 de 7 beside Buscar without changing Agregar, then hides 7 subidos after two seconds", async () => {
  const page = await workspace();
  const add = document.querySelector<HTMLElement>('[data-testid="business-primary-upload"]')!;
  const label = add.textContent;
  const width = add.getBoundingClientRect().width;
  const names = Array.from({ length: 7 }, (_, i) => `recibo-${i}.jpg`);
  await page.choose(...names);
  await page.close();
  const live = () => document.querySelector('[data-upload-announcement]')?.textContent;
  assert.equal(live(), "Subiendo 1 de 7");
  for (let i = 0; i < 2; i++) await page.act(async () => page.attempts[i].finish(page.receipt(names[i])));
  assert.equal(page.island()?.textContent, "3 de 7");
  assert.equal(page.island()?.getAttribute("aria-label"), "Subiendo 3 de 7");
  assert.equal(live(), "Subiendo 1 de 7", "only the start is announced during progress");
  const ring = page.island()?.querySelector("circle[stroke-dashoffset]");
  assert.ok(ring);
  assert.ok(Number(ring.getAttribute("stroke-dashoffset")) > 0 && Number(ring.getAttribute("stroke-dashoffset")) < 1);
  assert.equal(add.textContent, label);
  assert.equal(add.getBoundingClientRect().width, width);
  assert.ok(page.island()?.closest('[data-testid="business-bar-tools"]'));
  jest.useFakeTimers();
  for (let i = 2; i < 7; i++) await page.act(async () => page.attempts[i].finish(page.receipt(names[i])));
  assert.equal(page.island()?.textContent, "7 subidos");
  assert.equal(live(), "7 subidos");
  await page.act(async () => { jest.advanceTimersByTime(1999); });
  assert.ok(page.island());
  await page.act(async () => { jest.advanceTimersByTime(1); });
  assert.equal(page.island(), null, "the folding pill is no longer an action");
});

test("a failed file stays in red, opens at its retry control, and survives panel close until removed", async () => {
  const page = await workspace();
  await page.choose("bien.jpg", "fallo.jpg");
  await page.close();
  await page.act(async () => page.attempts[0].finish(page.receipt("bien")));
  jest.useFakeTimers();
  await page.act(async () => page.attempts[1].fail(new TypeError("Failed to fetch")));
  await page.act(async () => { jest.advanceTimersByTime(10000); });
  assert.equal(page.island()?.textContent, "1 sin subir");
  assert.match(page.island()?.className ?? "", /bg-\[#f6dfe0\]/);
  assert.match(page.island()?.className ?? "", /dark:text-\[#ec9aa0\]/);
  await page.click(page.island());
  assert.equal(page.island(), null);
  assert.equal(document.activeElement?.getAttribute("aria-label"), "Reintentar fallo.jpg");
  await page.close();
  assert.equal(page.island()?.textContent, "1 sin subir");
  assert.equal(document.activeElement?.getAttribute("data-testid"), "receipt-upload-island", "keyboard focus returns to the outstanding file");
  await page.click(page.island());
  assert.equal(page.dialog()?.querySelector('[data-testid="receipt-upload-saved-fold"]'), null);
  await page.click(page.dialog()?.querySelector<HTMLButtonElement>('[data-status="failed"] button:last-child[aria-label^="Quitar"]'));
  await page.close();
  assert.equal(page.island(), null);
});

test("a collapsed record displaces the island only as far as its edge, and expansion conceals it until closed", async () => {
  const page = await workspace(true);
  await page.choose("a.jpg", "b.jpg");
  await page.close();
  const live = () => document.querySelector("[data-upload-announcement]")?.textContent;
  assert.equal(live(), "Subiendo 1 de 2");
  await page.act(async () => page.state.business!.openPanel({ kind: "receipt", receiptId: "receipt-a", list: "inbox" }));
  const size = () => document.querySelector<HTMLButtonElement>('[data-testid="dossier-size"]');
  await page.until(() => Boolean(size()), "the real dossier is open");
  assert.equal(page.island(), null, "the expanded drawer covers the bar");
  await page.act(async () => page.attempts[0].finish(page.receipt("a")));
  assert.equal(live(), "Subiendo 1 de 2", "covering the island leaves the start announcement in place");
  const search = document.querySelector<HTMLElement>('[data-testid="stable-search"]')!;
  const drawer = document.querySelector<HTMLElement>('[role="region"][data-width="dossier"]')!;
  search.getBoundingClientRect = () => DOMRect.fromRect({ x: 900, width: 200 });
  drawer.getBoundingClientRect = () => DOMRect.fromRect({ x: 800, width: 640 });
  await page.click(size());
  assert.equal(page.island()?.textContent, "2 de 2");
  assert.equal(live(), "Subiendo 1 de 2");
  const anchor = document.querySelector<HTMLElement>('[data-upload-anchor]')!;
  assert.equal(anchor.style.getPropertyValue("--record-shift"), "104px", "900 - 8 - 104 = 788, 12px from the record");
  await page.click(size());
  assert.equal(page.island(), null);
  await page.click(drawer.querySelector<HTMLButtonElement>('button[aria-label="Cerrar"]'));
  assert.equal(page.island()?.textContent, "2 de 2");
  assert.equal(live(), "Subiendo 1 de 2");
  assert.equal(anchor.style.getPropertyValue("--record-shift"), "0px");
});

test("the island morphs into the panel and back only when motion is enabled", async () => {
  const original = window.matchMedia;
  const rect = HTMLElement.prototype.getBoundingClientRect;
  const animate = Element.prototype.animate;
  let reduced = false;
  const motions: Animation[] = [];
  window.matchMedia = query => {
    const media = original.call(window, query);
    if (query.includes("prefers-reduced-motion")) Object.defineProperty(media, "matches", { value: reduced });
    return media;
  };
  try {
    const page = await workspace();
    await page.choose("fallo.jpg");
    await page.close();
    HTMLElement.prototype.getBoundingClientRect = function () {
      return DOMRect.fromRect(this.matches('[role="dialog"]') ? { width: 610, height: 900 } : { x: 500, width: 110, height: 40 });
    };
    Element.prototype.animate = function () {
      const animation = { cancel() {} } as Animation;
      motions.push(animation);
      return animation;
    };
    for (const reduce of [false, true]) {
      reduced = reduce;
      for (const opening of [true, false]) {
        if (opening) await page.click(page.island());
        else await page.close();
        assert.equal(Boolean(page.dialog()), opening);
        assert.equal(Boolean(document.querySelector("[data-upload-morph]")), !reduce);
        assert.equal(motions.length, reduce ? 0 : 2);
        motions.splice(0).forEach(motion => motion.onfinish?.call(motion, {} as AnimationPlaybackEvent));
      }
      assert.equal(page.island()?.dataset.phase, "open");
    }
  } finally {
    HTMLElement.prototype.getBoundingClientRect = rect;
    Element.prototype.animate = animate;
    window.matchMedia = original;
  }
});

test("both languages have the short upload count and the existing accessible count", async () => {
  for (const [language, expected] of [["es-419", "{{position}} de {{total}}"], ["en", "{{position}} of {{total}}"]]) {
    const { business } = JSON.parse(await readFile(new URL(`../public/locales/${language}/common.json`, import.meta.url), "utf8"));
    assert.equal(business.intake.island_uploading, expected);
    assert.ok(business.intake.chip_uploading);
  }
});


test("the opening transform does not crop the label or its trailing padding", async () => {
  const page = await workspace();
  await page.choose("a.jpg");
  await page.close();
  const content = page.island()!.firstElementChild as HTMLElement;
  Object.defineProperty(content, "offsetWidth", { value: 110 });
  content.getBoundingClientRect = () => DOMRect.fromRect({ width: 94.6 });
  await page.act(async () => { window.dispatchEvent(new Event("resize")); });
  assert.equal(page.island()?.parentElement?.style.getPropertyValue("--island-width"), "112px");
});

test("an expired success stays silent when the phone or desktop header remounts", async () => {
  const page = await workspace();
  await page.choose("a.jpg");
  await page.close();
  jest.useFakeTimers();
  await page.act(async () => page.attempts[0].finish(page.receipt("a")));
  assert.equal(page.island()?.textContent, "1 subido");
  await page.act(async () => { jest.advanceTimersByTime(2100); });
  assert.equal(page.island(), null);
  for (const phone of [true, false]) {
    await page.act(async () => page.state.resize!(phone));
    assert.equal(page.island(), null, "resizing cannot restart the saved timer");
    assert.equal(document.querySelector("[data-upload-announcement]")?.textContent, "");
  }
});

test("retrying a failed file during the same upload keeps two distinct files in the ring", async () => {
  const page = await workspace();
  await page.choose("a.jpg", "b.jpg");
  await page.close();
  await page.act(async () => page.attempts[0].fail(new TypeError("Failed to fetch")));
  assert.equal(page.island()?.textContent, "2 de 2");
  await page.act(async () => { window.dispatchEvent(new Event("online")); });
  assert.equal(page.island()?.textContent, "2 de 2");
  await page.act(async () => page.attempts[1].finish(page.receipt("b")));
  assert.equal(page.attempts[2].key, page.attempts[0].key);
  assert.equal(page.island()?.textContent, "2 de 2", "a repeat attempt cannot become a third file");
  await page.act(async () => page.attempts[2].finish(page.receipt("a")));
  assert.equal(page.island()?.textContent, "2 subidos");
});
