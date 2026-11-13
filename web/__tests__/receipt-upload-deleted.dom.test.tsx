import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue, type BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import ReceiptIntakeDialog from "@/components/business-app/ReceiptIntakeDialog";
import { ReceiptUploadQueue } from "@/components/business-app/receipt-upload-queue";
import { TypedNoteQueue } from "@/components/business-app/typed-note-queue";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { ToastViewport } from "@/components/business-app/foundation/ToastViewport";
import { clearToasts } from "@/components/business-app/foundation/toasts";
import type { ReceiptSummary } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";

const limits = { max_bytes: 1024, media_types: ["text/plain"] };
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterEach(async () => { while (cleanups.length) await cleanups.pop()!(); clearToasts(); document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount({ count = 1, saved = 0, approve = true, available = true, failFirst = false, failRead = false, stillDeleted = false } = {}) {
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const base = await fixture.receipt("rcpt-ferreteria");
  const deletion = { actor: { actor_id: "c93a5c81-2f69-4c0d-932e-1a7c5526c941", display_name: "María Pérez" }, at: "2026-11-12T10:00:00Z", purge_at: "2026-11-19T10:00:00Z", key: "delete", previous_state: { state: "open", group: "attention" as const } };
  const receipts = new Map<string, ReceiptSummary>(Array.from({ length: count + saved }, (_, index) => {
    const id = `receipt-${index}`;
    return [id, { ...base, id, deleted: index < count ? deletion : null, restore_available: index < count && available }];
  }));
  const calls: { id: string; key: string }[] = [];
  const reads: string[] = [];
  const reviews: ReceiptSummary[][] = [];
  const panels: BusinessPanelState[] = [];
  const chosen = (await fixture.spaces())[0];
  const source = {
    ...fixture,
    restoreDocument: async (id: string, key: string) => {
      calls.push({ id, key });
      if (failFirst && calls.length === 1) throw new Error("synthetic outage");
      return { document_id: id, deleted: false };
    },
    receipt: async (id: string) => {
      reads.push(id);
      if (failRead && reads.length === 1) throw new Error("synthetic read outage");
      if (stillDeleted) return { ...base, id, deleted: deletion, restore_available: true };
      const receipt = { ...base, id, deleted: null, restore_available: false };
      receipts.set(id, receipt);
      return receipt;
    },
  };
  const queue = new ReceiptUploadQueue(async file => {
    const receipt = receipts.get(file.name.replace(".txt", ""));
    assert.ok(receipt);
    return receipt;
  }, () => undefined);
  queue.add([...receipts.keys()].map(id => new File(["receipt"], `${id}.txt`, { type: "text/plain" })), limits, "inbox");
  await queue.save("inbox", false);
  const context = {
    source, chosen: { ...chosen, capabilities: approve ? ["read", "approve"] : ["read", "prepare"] },
    records: { workspace: { accounts: [], currencies: [], assistant_available: false, chat_available: false, receipt_limits: limits }, error: false },
    bridge: null, reload() {}, openPanel: (panel: BusinessPanelState) => panels.push(panel),
  } as unknown as BusinessContextValue;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><ReceiptIntakeDialog target="inbox" queue={queue} notes={new TypedNoteQueue(() => undefined)} onClose={() => undefined} onReview={items => reviews.push(items)} /><ToastViewport /></BusinessContext.Provider></I18nextProvider>));
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const group = () => document.querySelector('[data-testid="receipt-upload-deleted-fold"]');
  const button = (text: string, within: ParentNode = document) => [...within.querySelectorAll<HTMLButtonElement>("button")].find(node => node.textContent?.trim() === text);
  const click = async (element: HTMLElement | null | undefined) => { assert.ok(element); await act(async () => element.click()); };
  const expand = async () => { await click(group()?.querySelector<HTMLButtonElement>('button[aria-expanded]')); };
  return { group, button, click, expand, calls, reads, reviews, panels, queue };
}

test("one deleted match starts collapsed, has no saved count or review footer, and expands without a success check", async () => {
  const page = await mount();
  assert.ok(page.group());
  assert.equal(page.group()?.querySelector("button")?.getAttribute("aria-expanded"), "false");
  assert.match(page.group()?.textContent ?? "", /1 eliminado antes/);
  assert.equal(document.querySelector('[data-testid="receipt-upload-row"]'), null);
  assert.equal(document.querySelector('[data-testid="receipt-intake-footer"]'), null);
  assert.equal(document.querySelector('[data-testid="receipt-upload-summary"]')?.textContent?.includes("guardado"), false);
  await page.expand();
  const row = page.group()?.querySelector('[data-testid="receipt-upload-row"]');
  assert.match(row?.textContent ?? "", /receipt-0.txt/);
  assert.match(row?.textContent ?? "", /Eliminado antes/);
  assert.equal(page.group()?.querySelector(".lucide-circle-check"), null);
  assert.ok(page.button("Restaurar", row!));
});

test("mixed uploads keep saved and deleted counts separate and review only saved receipts", async () => {
  const page = await mount({ count: 2, saved: 2 });
  assert.match(page.group()?.textContent ?? "", /2 eliminados antes/);
  assert.match(document.querySelector('[data-testid="receipt-upload-saved-fold"]')?.textContent ?? "", /2 guardados/);
  await page.click(page.button("Revisar los recibos guardados"));
  assert.deepEqual(page.reviews[0]?.map(receipt => receipt.id), ["receipt-2", "receipt-3"]);
});

test("one saved and one deleted match each have their own collapsed group", async () => {
  const page = await mount({ count: 1, saved: 1 });
  assert.match(page.group()?.textContent ?? "", /1 eliminado antes/);
  const saved = document.querySelector('[data-testid="receipt-upload-saved-fold"]');
  assert.ok(saved);
  assert.match(saved.textContent ?? "", /1 guardado/);
  assert.equal(saved.querySelector("button")?.getAttribute("aria-expanded"), "false");
  assert.equal(document.querySelector('[data-testid="receipt-upload-row"]'), null);
});

test("restore all rereads each server receipt and moves restored matches into saved", async () => {
  const page = await mount({ count: 2 });
  await page.click(page.button("Restaurar todos"));
  assert.deepEqual(page.calls.map(call => call.id), ["receipt-0", "receipt-1"]);
  assert.deepEqual(page.reads, ["receipt-0", "receipt-1"]);
  assert.equal(page.group(), null);
  assert.match(document.querySelector('[data-testid="receipt-upload-saved-fold"]')?.textContent ?? "", /2 guardados/);
  assert.equal(document.querySelectorAll('[data-testid="toast"]').length, 1);
  await page.click(page.button("Ver"));
  assert.deepEqual(page.panels, [{ kind: "inbox" }]);
});

test("a row restore keeps its success toast and Ver opens that receipt", async () => {
  const page = await mount();
  await page.expand();
  await page.click(page.button("Restaurar", page.group()!));
  assert.match(document.querySelector('[data-testid="toast"]')?.textContent ?? "", /Documento restaurado en la Bandeja/);
  await page.click(page.button("Ver"));
  assert.deepEqual(page.panels, [{ kind: "receipt", receiptId: "receipt-0", list: "inbox" }]);
});

test("the reread owns the group even when a restore response says success", async () => {
  const page = await mount({ stillDeleted: true });
  await page.click(page.button("Restaurar todos"));
  assert.ok(page.group());
  assert.equal(document.querySelector('[data-testid="receipt-intake-footer"]'), null);
  assert.equal(document.querySelector('[data-testid="toast"]'), null);
  await page.click(page.button("Restaurar todos"));
  assert.equal(page.calls[0]?.key, page.calls[1]?.key);
});

test("a partial bulk failure retains its row and retries with the same key", async () => {
  const page = await mount({ count: 2, failFirst: true });
  await page.click(page.button("Restaurar todos"));
  assert.match(page.group()?.textContent ?? "", /1 eliminado antes/);
  await page.expand();
  assert.match(page.group()?.textContent ?? "", /No se pudo restaurar el documento/);
  assert.match(page.group()?.textContent ?? "", /receipt-0.txt/);
  await page.click(page.button("Restaurar", page.group()!));
  assert.deepEqual(page.calls.map(call => call.id), ["receipt-0", "receipt-1", "receipt-0"]);
  assert.equal(page.calls[0]?.key, page.calls[2]?.key);
  assert.equal(page.group(), null);
});

test("a failed reread retains the deleted match and request key until retry confirms the server state", async () => {
  const page = await mount({ failRead: true });
  await page.click(page.button("Restaurar todos"));
  assert.ok(page.group());
  assert.equal(document.querySelector('[data-testid="receipt-intake-footer"]'), null);
  await page.click(page.button("Restaurar todos"));
  assert.equal(page.calls[0]?.key, page.calls[1]?.key);
  assert.equal(page.group(), null);
});

test("restore controls follow approve and the server's restore_available", async () => {
  for (const options of [{ approve: false }, { available: false }]) {
    const page = await mount(options);
    assert.equal(page.button("Restaurar todos"), undefined);
    await page.expand();
    assert.equal(page.button("Restaurar", page.group()!), undefined);
    await cleanups.pop()!();
    document.body.innerHTML = "";
  }
});
